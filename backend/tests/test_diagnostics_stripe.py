"""Stripe guided diagnostics — local evidence only, no outbound Stripe calls."""

from datetime import timedelta

import respx

from app.core.config import get_settings
from app.db.models.webhook import WebhookEventORM
from app.services import diagnostics as diagnostics_module
from tests.reliability_helpers import add_attempt, set_event_state, utcnow
from tests.stripe_helpers import make_event, post_event, store_event


def _run(client, integration_id) -> dict:
    response = client.post(f"/api/diagnostics/{integration_id}/run")
    assert response.status_code == 200, response.text
    return response.json()


def _checks(run: dict) -> dict[str, dict]:
    return {check["check_code"]: check for check in run["checks"]}


def test_configured_without_events_is_unknown(client, stripe_integration_id) -> None:
    run = _run(client, stripe_integration_id)
    checks = _checks(run)
    assert checks["stripe_webhook_secret"]["status"] == "pass"
    assert checks["stripe_verified_receipts"]["status"] == "unknown"
    assert "stripe trigger" in checks["stripe_verified_receipts"]["recommendation"]
    assert run["overall_status"] == "unknown"
    assert run["summary"].startswith("Insufficient evidence")


def test_missing_secret_fails(client, stripe_integration_id, monkeypatch) -> None:
    settings = get_settings().model_copy(update={"stripe_webhook_secret": None})
    monkeypatch.setattr(diagnostics_module, "get_settings", lambda: settings)
    run = _run(client, stripe_integration_id)
    secret = _checks(run)["stripe_webhook_secret"]
    assert secret["status"] == "fail"
    assert "503" in secret["evidence"]
    assert run["overall_status"] == "fail"


def test_healthy_processing_passes(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="processed")
    add_attempt(db_session, event, outcome="succeeded")
    run = _run(client, stripe_integration_id)
    assert run["overall_status"] == "pass"
    assert {c["status"] for c in run["checks"]} == {"pass"}
    assert list(_checks(run)) == [
        "stripe_webhook_secret",
        "stripe_verified_receipts",
        "stripe_duplicate_deliveries",
        "stripe_processing_backlog",
        "stripe_failed_queue",
        "stripe_stale_processing",
        "stripe_processing_outcomes",
        "stripe_retry_activity",
    ]


def test_duplicates_are_informational(client, db_session, stripe_integration_id) -> None:
    event = make_event(event_id="evt_diag_dup")
    post_event(client, stripe_integration_id, event)
    post_event(client, stripe_integration_id, event)
    stored = db_session.query(WebhookEventORM).one()
    set_event_state(db_session, stored, status="processed")
    add_attempt(db_session, stored, outcome="succeeded")
    run = _run(client, stripe_integration_id)
    dup = _checks(run)["stripe_duplicate_deliveries"]
    assert dup["status"] == "pass"
    assert dup["evidence"].startswith("1 duplicate")
    assert run["overall_status"] == "pass"


def test_failed_queue_is_warning_overall(client, db_session, stripe_integration_id) -> None:
    ok = store_event(db_session, stripe_integration_id, event_id="evt_ok")
    set_event_state(db_session, ok, status="processed")
    add_attempt(db_session, ok, outcome="succeeded")
    bad = store_event(db_session, stripe_integration_id, event_id="evt_bad")
    set_event_state(db_session, bad, status="failed", error_code="handler_error")
    add_attempt(db_session, bad, outcome="failed", error_code="handler_error")
    run = _run(client, stripe_integration_id)
    failed_queue = _checks(run)["stripe_failed_queue"]
    assert failed_queue["status"] == "fail"
    assert failed_queue["required"] is False
    assert "Failed Events" in failed_queue["recommendation"]
    assert run["overall_status"] == "warning"


def test_only_failed_attempts_warn_outcomes(client, db_session, stripe_integration_id) -> None:
    bad = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, bad, status="retry_scheduled", error_code="handler_error")
    add_attempt(db_session, bad, outcome="failed", error_code="handler_error", retry_delay_seconds=30)
    checks = _checks(_run(client, stripe_integration_id))
    assert checks["stripe_processing_outcomes"]["status"] == "warning"
    assert checks["stripe_processing_backlog"]["status"] == "warning"


def test_stale_processing_warns(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="processing", processing_started_at=utcnow() - timedelta(minutes=30))
    run = _run(client, stripe_integration_id)
    stale = _checks(run)["stripe_stale_processing"]
    assert stale["status"] == "warning"
    assert "reclaims" in stale["recommendation"]
    assert run["overall_status"] == "warning"


def test_stale_pending_backlog_warns(client, db_session, stripe_integration_id) -> None:
    store_event(db_session, stripe_integration_id, now=utcnow() - timedelta(minutes=45))
    backlog = _checks(_run(client, stripe_integration_id))["stripe_processing_backlog"]
    assert backlog["status"] == "warning"
    assert "1 older than 15 min" in backlog["evidence"]


def test_retry_activity_threshold(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="processed")
    for n in range(1, 6):
        add_attempt(db_session, event, outcome="failed", number=n, retry_delay_seconds=30)
    add_attempt(db_session, event, outcome="succeeded", number=6)
    retry = _checks(_run(client, stripe_integration_id))["stripe_retry_activity"]
    assert retry["status"] == "warning"
    assert retry["evidence"].startswith("5 processing retries")


def test_ignored_events_count_as_success(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id, event_type="customer.created")
    set_event_state(db_session, event, status="ignored")
    add_attempt(db_session, event, outcome="ignored")
    run = _run(client, stripe_integration_id)
    assert _checks(run)["stripe_processing_outcomes"]["status"] == "pass"
    assert run["overall_status"] == "pass"


@respx.mock
def test_no_outbound_calls_and_no_mutation(client, db_session, stripe_integration_id) -> None:
    event = store_event(db_session, stripe_integration_id)
    set_event_state(db_session, event, status="failed", error_code="handler_error")
    run = _run(client, stripe_integration_id)
    assert len(respx.calls) == 0
    db_session.expire_all()
    after = db_session.get(WebhookEventORM, event.id)
    assert after.processing_status == "failed"
    assert after.attempt_count == 4
    text = str(run)
    assert "whsec_" not in text
    assert "stripe-signature" not in text.lower()
    assert '"payload"' not in text
