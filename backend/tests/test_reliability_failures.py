"""Recent failure aggregation across provider requests, webhooks, Failure Lab, diagnostics."""

from datetime import timedelta

import pytest

from tests.reliability_helpers import (
    add_log,
    connect_github_directly,
    github_integration,
    set_event_state,
    utcnow,
)
from tests.stripe_helpers import store_event


def _failures(client, **params) -> list[dict]:
    response = client.get("/api/reliability/failures", params=params)
    assert response.status_code == 200
    return response.json()


def _run_lab(client, integration_id, scenario: str = "provider_500") -> None:
    response = client.post(
        "/api/failure-lab/run", json={"integration_id": str(integration_id), "scenario": scenario}
    )
    assert response.status_code == 200


def test_empty_when_nothing_failed(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id)
    assert _failures(client) == []


def test_real_provider_failure_listed(client, db_session) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, status_code=500, error="github_server_error", latency_ms=250)
    [item] = _failures(client)
    assert item["source"] == "provider_request"
    assert item["severity"] == "error"
    assert item["code"] == "github_server_error"
    assert item["integration_name"] == "GitHub"
    assert item["simulated"] is False
    assert item["status_code"] == 500
    assert item["endpoint"] == "/user"
    assert item["id"].startswith("request:")


@pytest.mark.parametrize(
    "status_code,error,severity",
    [
        (429, "github_rate_limited", "warning"),
        (500, "github_server_error", "error"),
        (401, "github_unauthorized", "error"),
        (None, "github_timeout", "error"),
    ],
)
def test_provider_failure_severity(client, db_session, status_code, error, severity) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, status_code=status_code, error=error)
    [item] = _failures(client)
    assert item["severity"] == severity
    assert item["severity"] != "critical"


def test_simulations_hidden_by_default(client, db_session) -> None:
    gh = github_integration(db_session)
    _run_lab(client, gh.id)
    assert _failures(client) == []
    overview = client.get("/api/reliability/overview").json()
    assert overview["recent_failures"] == []


def test_include_simulated_adds_failure_lab_items(client, db_session) -> None:
    gh = github_integration(db_session)
    _run_lab(client, gh.id)
    items = _failures(client, include_simulated="true")
    assert len(items) == 1
    item = items[0]
    assert item["source"] == "failure_lab"
    assert item["simulated"] is True
    assert item["severity"] == "info"
    assert item["summary"].startswith("Simulation:")
    assert item["diagnosis_title"]


def test_simulated_request_log_not_double_counted(client, db_session) -> None:
    gh = github_integration(db_session)
    _run_lab(client, gh.id, "unauthorized_401")
    items = _failures(client, include_simulated="true")
    assert [i["source"] for i in items] == ["failure_lab"]


def test_source_failure_lab_explicit(client, db_session) -> None:
    gh = github_integration(db_session)
    _run_lab(client, gh.id)
    add_log(db_session, gh.id, status_code=500, error="github_server_error")
    items = _failures(client, source="failure_lab")
    assert [i["source"] for i in items] == ["failure_lab"]


def test_stripe_failed_and_retry_events_listed(client, db_session, stripe_integration_id) -> None:
    failed = store_event(db_session, stripe_integration_id, event_id="evt_f")
    set_event_state(db_session, failed, status="failed", error_code="handler_error")
    retry = store_event(db_session, stripe_integration_id, event_id="evt_r")
    set_event_state(db_session, retry, status="retry_scheduled", error_code="handler_error")
    processed = store_event(db_session, stripe_integration_id, event_id="evt_p")
    set_event_state(db_session, processed, status="processed")
    store_event(db_session, stripe_integration_id, event_id="evt_pending")

    items = _failures(client, source="webhook_processing")
    by_event = {i["webhook_event_id"]: i for i in items}
    assert set(by_event) == {str(failed.id), str(retry.id)}
    assert by_event[str(failed.id)]["severity"] == "error"
    assert by_event[str(retry.id)]["severity"] == "warning"
    assert by_event[str(failed.id)]["code"] == "handler_error"
    assert by_event[str(failed.id)]["event_type"] == "payment_intent.succeeded"
    assert all(i["provider"] == "stripe" for i in items)


def test_provider_filter(client, db_session, stripe_integration_id) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, status_code=500, error="github_server_error")
    failed = store_event(db_session, stripe_integration_id, event_id="evt_pf")
    set_event_state(db_session, failed, status="failed", error_code="handler_error")

    assert {i["provider"] for i in _failures(client, provider="github")} == {"github"}
    assert {i["provider"] for i in _failures(client, provider="stripe")} == {"stripe"}
    assert len(_failures(client)) == 2


def test_integration_filter(client, db_session, github_integration_id) -> None:
    gh = github_integration(db_session)
    add_log(db_session, gh.id, status_code=500, error="github_server_error")
    add_log(db_session, github_integration_id, status_code=502, error="github_server_error")
    items = _failures(client, integration_id=github_integration_id)
    assert [i["integration_id"] for i in items] == [github_integration_id]


def test_sorted_newest_first_and_limited(client, db_session) -> None:
    gh = github_integration(db_session)
    base = utcnow() - timedelta(hours=2)
    for i in range(5):
        add_log(db_session, gh.id, status_code=500, error="github_server_error", at=base + timedelta(minutes=i))
    items = _failures(client, limit=3)
    assert len(items) == 3
    times = [i["occurred_at"] for i in items]
    assert times == sorted(times, reverse=True)


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_validation(client, limit) -> None:
    assert client.get("/api/reliability/failures", params={"limit": limit}).status_code == 422


def test_invalid_source_rejected(client) -> None:
    assert client.get("/api/reliability/failures", params={"source": "nonsense"}).status_code == 422


def test_failed_diagnostic_listed(client, db_session) -> None:
    gh = github_integration(db_session)
    run = client.post(f"/api/diagnostics/{gh.id}/run").json()
    items = _failures(client, source="diagnostic")
    assert len(items) == 1
    assert items[0]["diagnostic_run_id"] == run["id"]
    assert items[0]["code"] == "github_credential"
    assert items[0]["severity"] == "error"


def test_passing_diagnostic_not_listed(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="processed")
    client.post(f"/api/diagnostics/{stripe_integration_id}/run")
    assert _failures(client, source="diagnostic") == []


def test_old_failures_outside_window(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, status_code=500, error="github_server_error", at=utcnow() - timedelta(days=10))
    assert _failures(client) == []
    assert _failures(client, window_hours=168) == []
    assert client.get("/api/reliability/failures", params={"window_hours": 169}).status_code == 422
