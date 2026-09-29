"""Reliability overview + integration detail via the API (passive read path)."""

from datetime import timedelta

import pytest
import respx
from httpx import Response

from app.core.config import get_settings
from app.services import reliability as reliability_module
from tests.reliability_helpers import (
    add_log,
    connect_github_directly,
    github_integration,
    set_event_state,
    utcnow,
)
from tests.stripe_helpers import make_event, post_event, store_event


def _health(body: dict, provider: str) -> dict:
    return next(item for item in body["integrations"] if item["provider"] == provider)


def _no_webhook_secret(monkeypatch) -> None:
    settings = get_settings().model_copy(update={"stripe_webhook_secret": None})
    monkeypatch.setattr(reliability_module, "get_settings", lambda: settings)


def test_overview_seeded_state(client) -> None:
    response = client.get("/api/reliability/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["window_hours"] == 24
    assert body["system"]["database"] == "healthy"
    github = _health(body, "github")
    stripe = _health(body, "stripe")
    assert github["health"] == "not_configured"
    assert github["configuration"] == "Not connected"
    assert stripe["health"] == "unknown"
    assert stripe["configuration"] == "Webhook verification configured"
    assert body["totals"] == {
        "healthy": 0,
        "degraded": 0,
        "failed": 0,
        "unknown": 1,
        "not_configured": 1,
    }
    assert body["recent_failures"] == []
    assert body["operational"]["real_provider_requests"] == 0


@pytest.mark.parametrize("hours,expected", [(0, 422), (169, 422), (1, 200), (168, 200)])
def test_overview_window_validation(client, hours, expected) -> None:
    assert client.get("/api/reliability/overview", params={"window_hours": hours}).status_code == expected


def test_totals_match_integration_healths(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, status_code=401, error="github_unauthorized")
    client.post("/api/integrations", json={"name": "Second GitHub", "provider": "github"})

    body = client.get("/api/reliability/overview").json()
    counted: dict[str, int] = {}
    for item in body["integrations"]:
        counted[item["health"]] = counted.get(item["health"], 0) + 1
    for state, count in body["totals"].items():
        assert counted.get(state, 0) == count
    assert body["totals"]["failed"] == 1
    assert body["totals"]["not_configured"] == 1


@respx.mock(assert_all_called=False)
def test_overview_makes_no_provider_calls(client, db_session, respx_mock) -> None:
    github_api = respx_mock.route(host="api.github.com").mock(return_value=Response(200, json={}))
    stripe_api = respx_mock.route(host="api.stripe.com").mock(return_value=Response(200, json={}))
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id)

    assert client.get("/api/reliability/overview").status_code == 200
    assert client.get(f"/api/reliability/integrations/{gh.id}").status_code == 200
    assert client.get("/api/reliability/failures").status_code == 200
    assert not github_api.called
    assert not stripe_api.called


def test_github_connected_without_evidence_is_unknown(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["health"] == "unknown"
    assert github["request_metrics"]["request_count"] == 0


def test_github_healthy_with_real_success(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, latency_ms=180)
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["health"] == "healthy"
    assert github["request_metrics"]["latest_status_code"] == 200
    assert github["request_metrics"]["latest_latency_band"] == "normal"
    assert any("0 / 1 real requests failed" in line for line in github["evidence"])


def test_github_latest_401_is_failed_with_sample_size(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, status_code=401, error="github_unauthorized")
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["health"] == "failed"
    assert any("1 / 1 real requests failed" in line for line in github["evidence"])
    assert github["recommended_action"]


def test_github_needs_setup_is_failed(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    gh = github_integration(db_session)
    gh.status = "needs_setup"
    db_session.commit()
    assert _health(client.get("/api/reliability/overview").json(), "github")["health"] == "failed"


@pytest.mark.parametrize(
    "status_code,error",
    [(429, "github_rate_limited"), (503, "github_server_error"), (None, "github_timeout")],
)
def test_github_transient_failures_are_degraded(client, db_session, status_code, error) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, at=utcnow() - timedelta(minutes=5))
    add_log(db_session, gh.id, status_code=status_code, error=error)
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["health"] == "degraded"
    assert github["request_metrics"]["latest_error_code"] == error


def test_github_simulations_do_not_affect_health(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, at=utcnow() - timedelta(minutes=1))
    for _ in range(5):
        add_log(db_session, gh.id, status_code=500, error="github_server_error", simulated=True)
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["health"] == "healthy"
    assert github["request_metrics"]["request_count"] == 1


def test_github_slow_latency_is_degraded(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, latency_ms=2400)
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["health"] == "degraded"
    assert github["request_metrics"]["latest_latency_band"] == "slow"


def test_stripe_processed_events_are_healthy(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="processed")
    stripe = _health(client.get("/api/reliability/overview").json(), "stripe")
    assert stripe["health"] == "healthy"
    assert stripe["webhook_metrics"]["processed"] == 1


def test_stripe_duplicates_alone_stay_healthy(client, stripe_integration_id) -> None:
    event = make_event(event_id="evt_dup_rel")
    assert post_event(client, stripe_integration_id, event).status_code == 200
    assert post_event(client, stripe_integration_id, event).json()["duplicate"] is True
    body = client.get("/api/reliability/overview").json()
    stripe = _health(body, "stripe")
    assert stripe["health"] == "healthy"
    assert stripe["webhook_metrics"]["duplicate_deliveries"] == 1
    assert body["operational"]["duplicate_webhook_deliveries"] == 1
    assert body["operational"]["webhook_events_received"] == 1


def test_stripe_failed_event_is_degraded(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="failed", error_code="handler_error")
    stripe = _health(client.get("/api/reliability/overview").json(), "stripe")
    assert stripe["health"] == "degraded"
    assert stripe["webhook_metrics"]["failed"] == 1
    assert "Failed Events" in stripe["recommended_action"]


def test_stripe_retry_scheduled_is_degraded(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="retry_scheduled", error_code="handler_error")
    stripe = _health(client.get("/api/reliability/overview").json(), "stripe")
    assert stripe["health"] == "degraded"
    assert stripe["webhook_metrics"]["retry_scheduled"] == 1


def test_stripe_stale_processing_is_degraded(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(
        db_session, event, status="processing", processing_started_at=utcnow() - timedelta(minutes=20)
    )
    stripe = _health(client.get("/api/reliability/overview").json(), "stripe")
    assert stripe["health"] == "degraded"
    assert stripe["webhook_metrics"]["stale_processing"] == 1


def test_stripe_fresh_pending_is_not_degraded(client, db_session, stripe_integration_id) -> None:
    store_event(db_session, stripe_integration_id)
    stripe = _health(client.get("/api/reliability/overview").json(), "stripe")
    assert stripe["health"] == "healthy"
    assert stripe["webhook_metrics"]["pending"] == 1
    assert stripe["webhook_metrics"]["stale_pending"] == 0


def test_stripe_missing_secret_is_not_configured(client, monkeypatch) -> None:
    _no_webhook_secret(monkeypatch)
    stripe = _health(client.get("/api/reliability/overview").json(), "stripe")
    assert stripe["health"] == "not_configured"
    assert stripe["configuration"] == "Webhook verification not configured"
    assert stripe["webhook_metrics"]["verification_configured"] is False


def test_integration_detail_github(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, at=utcnow() - timedelta(minutes=2))
    add_log(db_session, gh.id, status_code=500, error="github_server_error")
    response = client.get(f"/api/reliability/integrations/{gh.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["health"] == "degraded"
    assert len(body["recent_requests"]) == 2
    assert body["recent_requests"][0]["status_code"] == 500
    assert body["recent_webhook_events"] == []
    assert [f["code"] for f in body["recent_failures"]] == ["github_server_error"]


def test_integration_detail_stripe_lists_events(client, db_session, stripe_integration_id) -> None:
    store_event(db_session, stripe_integration_id, event_id="evt_detail_1")
    body = client.get(f"/api/reliability/integrations/{stripe_integration_id}").json()
    assert body["provider"] == "stripe"
    assert [e["provider_event_id"] for e in body["recent_webhook_events"]] == ["evt_detail_1"]
    assert body["request_metrics"] is None


def test_integration_detail_unknown_is_404(client) -> None:
    response = client.get("/api/reliability/integrations/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404


def test_overview_does_not_mutate_integrations(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, status_code=401, error="github_unauthorized")
    before = client.get("/api/integrations").json()
    client.get("/api/reliability/overview")
    client.get(f"/api/reliability/integrations/{gh.id}")
    assert client.get("/api/integrations").json() == before


def test_latest_diagnostic_brief_appears_on_overview(client, db_session) -> None:
    gh = github_integration(db_session)
    run = client.post(f"/api/diagnostics/{gh.id}/run").json()
    github = _health(client.get("/api/reliability/overview").json(), "github")
    assert github["latest_diagnostic"]["id"] == run["id"]
    assert github["latest_diagnostic"]["overall_status"] == "fail"
