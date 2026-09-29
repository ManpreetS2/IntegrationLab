"""Request / webhook / operational metrics correctness."""

from datetime import timedelta

import pytest

from tests.reliability_helpers import (
    add_attempt,
    add_log,
    connect_github_directly,
    github_integration,
    set_event_state,
    utcnow,
)
from tests.stripe_helpers import store_event


def _github_metrics(client, **params) -> dict:
    body = client.get("/api/reliability/overview", params=params).json()
    return next(i for i in body["integrations"] if i["provider"] == "github")["request_metrics"]


def test_real_request_counts_exclude_simulations(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id)
    add_log(db_session, gh.id, status_code=500, error="github_server_error")
    add_log(db_session, gh.id, status_code=401, error="github_unauthorized", simulated=True)
    metrics = _github_metrics(client)
    assert metrics["request_count"] == 2
    assert metrics["success_count"] == 1
    assert metrics["failure_count"] == 1
    assert metrics["error_rate"] == 0.5


def test_p95_is_nearest_rank_and_deterministic(client, db_session) -> None:
    gh = github_integration(db_session)
    base = utcnow() - timedelta(minutes=30)
    for i in range(1, 21):
        add_log(db_session, gh.id, latency_ms=i * 10, at=base + timedelta(seconds=i))
    first = _github_metrics(client)
    second = _github_metrics(client)
    assert first["p95_latency_ms"] == 190
    assert first["average_latency_ms"] == 105
    assert first["latest_latency_ms"] == 200
    assert first == second


def test_single_sample_is_preserved(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, latency_ms=321)
    metrics = _github_metrics(client)
    assert metrics["request_count"] == 1
    assert metrics["p95_latency_ms"] == 321
    assert metrics["average_latency_ms"] == 321


def test_no_requests_gives_null_rates(client) -> None:
    metrics = _github_metrics(client)
    assert metrics["request_count"] == 0
    assert metrics["error_rate"] is None
    assert metrics["p95_latency_ms"] is None


def test_transport_failure_without_status_counts_as_failure(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, status_code=None, error="github_timeout", latency_ms=15000)
    metrics = _github_metrics(client)
    assert metrics["failure_count"] == 1
    assert metrics["latest_status_code"] is None
    assert metrics["latest_error_code"] == "github_timeout"


def test_window_filtering(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, at=utcnow() - timedelta(hours=30))
    add_log(db_session, gh.id, at=utcnow() - timedelta(hours=1))
    assert _github_metrics(client)["request_count"] == 1
    assert _github_metrics(client, window_hours=48)["request_count"] == 2
    assert _github_metrics(client, window_hours=1)["request_count"] == 0


def test_rate_limit_remaining_reported(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, rate_limit_remaining=42)
    body = client.get("/api/reliability/overview").json()
    github = next(i for i in body["integrations"] if i["provider"] == "github")
    assert github["request_metrics"]["rate_limit_remaining"] == 42
    assert github["health"] == "degraded"


def test_request_metrics_endpoint_filters(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, latency_ms=100)
    add_log(db_session, gh.id, latency_ms=300, status_code=404, error="github_not_found")
    add_log(db_session, gh.id, latency_ms=900, simulated=True, status_code=500, error="github_server_error")

    real = client.get(
        "/api/reliability/request-metrics", params={"provider": "github", "is_simulated": "false"}
    ).json()
    assert real["metrics"]["request_count"] == 2
    assert real["metrics"]["failure_count"] == 1
    assert real["metrics"]["average_latency_ms"] == 200

    everything = client.get("/api/reliability/request-metrics", params={"provider": "github"}).json()
    assert everything["metrics"]["request_count"] == 3
    assert everything["is_simulated"] is None

    simulated = client.get("/api/reliability/request-metrics", params={"is_simulated": "true"}).json()
    assert simulated["metrics"]["request_count"] == 1
    assert simulated["metrics"]["latest_status_code"] == 500


def test_request_metrics_by_integration(client, db_session, github_integration_id) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id)
    add_log(db_session, github_integration_id)
    add_log(db_session, github_integration_id)
    body = client.get(
        "/api/reliability/request-metrics", params={"integration_id": github_integration_id}
    ).json()
    assert body["metrics"]["request_count"] == 2


@pytest.mark.parametrize("hours", [0, 169])
def test_request_metrics_window_validation(client, hours) -> None:
    assert client.get("/api/reliability/request-metrics", params={"window_hours": hours}).status_code == 422


def test_webhook_attempt_metrics(client, db_session, stripe_integration_id) -> None:
    ok = store_event(db_session, stripe_integration_id, event_id="evt_ok")
    set_event_state(db_session, ok, status="processed")
    add_attempt(db_session, ok, outcome="succeeded")
    bad = store_event(db_session, stripe_integration_id, event_id="evt_bad")
    set_event_state(db_session, bad, status="retry_scheduled", error_code="handler_error")
    add_attempt(db_session, bad, outcome="failed", error_code="handler_error", retry_delay_seconds=30)
    ignored = store_event(db_session, stripe_integration_id, event_id="evt_ignored", event_type="customer.created")
    set_event_state(db_session, ignored, status="ignored")
    add_attempt(db_session, ignored, outcome="ignored")

    body = client.get("/api/reliability/overview").json()
    stripe = next(i for i in body["integrations"] if i["provider"] == "stripe")["webhook_metrics"]
    assert stripe["events_total"] == 3
    assert stripe["successful_attempts_in_window"] == 2
    assert stripe["failed_attempts_in_window"] == 1
    assert stripe["retries_scheduled_in_window"] == 1
    assert stripe["ignored"] == 1
    assert body["operational"]["webhook_processed"] == 1
    assert body["operational"]["webhook_retry_scheduled"] == 1


def test_operational_metrics(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id)
    add_log(db_session, gh.id, status_code=500, error="github_server_error")
    client.post("/api/failure-lab/run", json={"integration_id": str(gh.id), "scenario": "provider_500"})
    client.post(f"/api/diagnostics/{gh.id}/run")

    operational = client.get("/api/reliability/overview").json()["operational"]
    assert operational["real_provider_requests"] == 2
    assert operational["real_provider_errors"] == 1
    assert operational["simulated_requests"] == 1
    assert operational["failure_lab_runs"] == 1
    assert operational["diagnostic_runs"] == 1


def test_old_webhook_events_outside_window(client, db_session, stripe_integration_id) -> None:
    old = store_event(db_session, stripe_integration_id, event_id="evt_old")
    set_event_state(db_session, old, status="processed", first_received_at=utcnow() - timedelta(days=3))
    body = client.get("/api/reliability/overview").json()
    stripe = next(i for i in body["integrations"] if i["provider"] == "stripe")
    assert stripe["webhook_metrics"]["events_total"] == 1
    assert stripe["webhook_metrics"]["events_in_window"] == 0
    assert body["operational"]["webhook_events_received"] == 0
    assert stripe["health"] == "healthy"
