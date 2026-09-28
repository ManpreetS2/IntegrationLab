"""Operator APIs: list, detail, process, process-due, failed queue, retry, dismiss."""

from __future__ import annotations

from app.services.webhook_handlers import PermanentWebhookError, default_handler_registry
from tests.stripe_helpers import make_event, post_event

BASE = "/api/webhooks/stripe"


def _receive(client, integration_id, **kwargs) -> str:
    """Deliver an event and return the internal webhook event id."""
    response = post_event(client, integration_id, make_event(**kwargs))
    assert response.status_code == 200
    events = client.get(f"{BASE}/events", params={"limit": 100}).json()
    return next(e["id"] for e in events if e["provider_event_id"] == response.json()["event_id"])


def _failed_event(client, integration_id, event_id="evt_fail") -> str:
    internal_id = _receive(client, integration_id, event_id=event_id, object_id=None)
    assert client.post(f"{BASE}/events/{internal_id}/process").json()["processing_status"] == "failed"
    return internal_id


def test_list_is_newest_first_and_filterable(client, stripe_integration_id):
    _receive(client, stripe_integration_id, event_id="evt_old")
    _receive(client, stripe_integration_id, event_type="charge.refunded", event_id="evt_new", object_id="ch_1")

    events = client.get(f"{BASE}/events").json()
    assert [e["provider_event_id"] for e in events] == ["evt_new", "evt_old"]

    refunds = client.get(f"{BASE}/events", params={"event_type": "charge.refunded"}).json()
    assert [e["provider_event_id"] for e in refunds] == ["evt_new"]

    pending = client.get(f"{BASE}/events", params={"status": "pending"}).json()
    assert len(pending) == 2
    by_integration = client.get(f"{BASE}/events", params={"integration_id": str(stripe_integration_id)}).json()
    assert len(by_integration) == 2
    assert len(client.get(f"{BASE}/events", params={"limit": 1}).json()) == 1


def test_list_validation(client):
    assert client.get(f"{BASE}/events", params={"limit": 0}).status_code == 422
    assert client.get(f"{BASE}/events", params={"limit": 101}).status_code == 422
    assert client.get(f"{BASE}/events", params={"status": "bogus"}).status_code == 422
    assert client.post(f"{BASE}/process-due", params={"limit": 51}).status_code == 422


def test_detail_includes_effects_and_attempts_without_raw_data(client, stripe_integration_id):
    internal_id = _receive(client, stripe_integration_id)
    client.post(f"{BASE}/events/{internal_id}/process")
    # Redelivery after processing.
    post_event(client, stripe_integration_id, make_event())

    detail = client.get(f"{BASE}/events/{internal_id}").json()
    assert detail["processing_status"] == "processed"
    assert detail["signature_verified"] is True
    assert detail["delivery_count"] == 2
    assert [e["effect_type"] for e in detail["effects"]] == ["payment_success_recorded"]
    assert [a["outcome"] for a in detail["attempts"]] == ["succeeded"]
    assert detail["attempts"][0]["manual"] is True
    for forbidden in ("raw", "payload", "signature_header", "whsec_"):
        assert forbidden not in str(detail.keys()) + str(detail.values())


def test_unknown_event_returns_404(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"{BASE}/events/{missing}").status_code == 404
    assert client.post(f"{BASE}/events/{missing}/process").status_code == 404
    assert client.post(f"{BASE}/events/{missing}/retry").status_code == 404
    assert client.post(f"{BASE}/events/{missing}/dismiss").status_code == 404


def test_process_endpoint_rejects_already_processed(client, stripe_integration_id):
    internal_id = _receive(client, stripe_integration_id)
    assert client.post(f"{BASE}/events/{internal_id}/process").status_code == 200
    again = client.post(f"{BASE}/events/{internal_id}/process")
    assert again.status_code == 409
    assert len(client.get(f"{BASE}/events/{internal_id}").json()["effects"]) == 1


def test_process_due_returns_counts(client, stripe_integration_id):
    _receive(client, stripe_integration_id, event_id="evt_ok")
    _receive(client, stripe_integration_id, event_type="customer.created", event_id="evt_unknown")
    _receive(client, stripe_integration_id, event_id="evt_bad", object_id=None)

    counts = client.post(f"{BASE}/process-due").json()
    assert counts == {"processed": 1, "retry_scheduled": 0, "failed": 1, "ignored": 1, "skipped": 0}

    summary = client.get(f"{BASE}/summary").json()
    assert summary["received"] == 3
    assert summary["processed"] == 1
    assert summary["failed"] == 1
    assert summary["ignored"] == 1
    assert summary["pending"] == 0


def test_failed_queue_lists_failed_events(client, stripe_integration_id):
    _receive(client, stripe_integration_id, event_id="evt_ok")
    failed_id = _failed_event(client, stripe_integration_id)

    failed = client.get(f"{BASE}/failed").json()
    assert [e["id"] for e in failed] == [failed_id]
    assert failed[0]["last_error_code"] == "webhook_invalid_event_data"


def test_manual_retry_opens_new_cycle_and_preserves_history(client, stripe_integration_id, monkeypatch):
    def reject(event):
        raise PermanentWebhookError("webhook_invalid_event_data", "Bad data.")

    monkeypatch.setitem(default_handler_registry._handlers, "payment_intent.succeeded", reject)
    internal_id = _receive(client, stripe_integration_id)
    failed = client.post(f"{BASE}/events/{internal_id}/process").json()
    assert failed["processing_status"] == "failed"

    retried = client.post(f"{BASE}/events/{internal_id}/retry")
    assert retried.status_code == 200
    body = retried.json()
    assert body["processing_status"] == "pending"
    assert body["manual_retry_count"] == 1
    assert body["retry_cycle"] == 2
    assert body["cycle_attempt_count"] == 0
    assert body["failed_at"] is None
    assert body["next_attempt_at"] is not None
    assert len(body["attempts"]) == 1

    monkeypatch.undo()
    counts = client.post(f"{BASE}/process-due").json()
    assert counts["processed"] == 1

    detail = client.get(f"{BASE}/events/{internal_id}").json()
    assert detail["processing_status"] == "processed"
    assert [(a["retry_cycle"], a["outcome"]) for a in detail["attempts"]] == [
        (1, "failed"),
        (2, "succeeded"),
    ]
    assert len(detail["effects"]) == 1


def test_retry_rejects_non_failed_events(client, stripe_integration_id):
    internal_id = _receive(client, stripe_integration_id)
    assert client.post(f"{BASE}/events/{internal_id}/retry").status_code == 409


def test_dismiss_stops_processing_and_keeps_history(client, stripe_integration_id):
    failed_id = _failed_event(client, stripe_integration_id)

    dismissed = client.post(f"{BASE}/events/{failed_id}/dismiss")
    assert dismissed.status_code == 200
    body = dismissed.json()
    assert body["processing_status"] == "dismissed"
    assert body["dismissed_at"] is not None
    assert len(body["attempts"]) == 1

    assert client.post(f"{BASE}/process-due").json()["failed"] == 0
    assert client.post(f"{BASE}/events/{failed_id}/process").status_code == 409
    assert client.get(f"{BASE}/failed").json() == []
    assert client.get(f"{BASE}/events/{failed_id}").json()["attempts"][0]["outcome"] == "failed"


def test_dismiss_rejects_processed_events(client, stripe_integration_id):
    internal_id = _receive(client, stripe_integration_id)
    client.post(f"{BASE}/events/{internal_id}/process")
    assert client.post(f"{BASE}/events/{internal_id}/dismiss").status_code == 409


def test_dismissed_event_can_be_reopened_with_retry(client, stripe_integration_id):
    failed_id = _failed_event(client, stripe_integration_id)
    client.post(f"{BASE}/events/{failed_id}/dismiss")

    reopened = client.post(f"{BASE}/events/{failed_id}/retry").json()
    assert reopened["processing_status"] == "pending"
    assert reopened["dismissed_at"] is None


def test_no_secret_in_operator_responses(client, stripe_integration_id):
    internal_id = _receive(client, stripe_integration_id)
    for path in (f"{BASE}/events", f"{BASE}/events/{internal_id}", f"{BASE}/summary", f"{BASE}/failed"):
        assert "whsec_" not in client.get(path).text
