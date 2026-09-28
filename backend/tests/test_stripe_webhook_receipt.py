"""Phase A: signature verification, durable receipt, and delivery-level idempotency."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

from sqlalchemy import func, select

from app.db.models.oauth import ProviderRequestLogORM
from app.db.models.webhook import WebhookEventORM, WebhookProcessingAttemptORM
from app.services import stripe_webhooks as receiver_module
from tests.stripe_helpers import TEST_WEBHOOK_SECRET, make_event, post_event, post_signed, sign


def _event_rows(db_session) -> list[WebhookEventORM]:
    db_session.expire_all()
    return list(db_session.scalars(select(WebhookEventORM)).all())


def _assert_small_safe_error(response, *secrets: str) -> None:
    body = response.text
    assert len(body) < 200
    for value in (TEST_WEBHOOK_SECRET, *secrets):
        assert value not in body


def test_valid_signature_is_received_and_stored(client, db_session, stripe_integration_id):
    response = post_event(client, stripe_integration_id, make_event())

    assert response.status_code == 200
    assert response.json() == {"received": True, "duplicate": False, "event_id": "evt_test_1"}

    rows = _event_rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.processing_status == "pending"
    assert row.delivery_count == 1
    assert row.attempt_count == 0
    assert row.event_type == "payment_intent.succeeded"
    assert row.provider_object_id == "pi_test_1"
    assert row.amount == 2000
    assert row.currency == "usd"
    assert row.livemode is False
    assert row.api_version == "2024-06-20"
    assert row.provider_created_at is not None


def test_receipt_does_not_process_inline(client, db_session, stripe_integration_id):
    post_event(client, stripe_integration_id, make_event())
    db_session.expire_all()
    attempts = db_session.scalar(select(func.count(WebhookProcessingAttemptORM.id)))
    assert attempts == 0


def test_missing_signature_rejected(client, db_session, stripe_integration_id):
    response = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=json.dumps(make_event()).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing Stripe-Signature header"}
    assert _event_rows(db_session) == []


def test_invalid_signature_rejected(client, db_session, stripe_integration_id):
    payload = json.dumps(make_event())
    wrong_header = sign(payload, secret="whsec_wrong_example")
    response = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=payload.encode(),
        headers={"Stripe-Signature": wrong_header},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid webhook signature"}
    _assert_small_safe_error(response, wrong_header, payload)
    assert _event_rows(db_session) == []


def test_garbage_signature_header_rejected(client, db_session, stripe_integration_id):
    response = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=json.dumps(make_event()).encode(),
        headers={"Stripe-Signature": "not-a-real-signature"},
    )
    assert response.status_code == 400
    assert _event_rows(db_session) == []


def test_expired_timestamp_rejected_with_default_tolerance(client, db_session, stripe_integration_id):
    payload = json.dumps(make_event())
    response = post_signed(client, stripe_integration_id, payload, timestamp=int(time.time()) - 3600)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid webhook signature"}
    assert _event_rows(db_session) == []


def test_raw_body_is_verified_byte_for_byte(client, db_session, stripe_integration_id):
    """A semantically identical but re-serialized body must fail verification."""
    compact = json.dumps(make_event(), separators=(",", ":"))
    pretty = json.dumps(make_event(), indent=2)
    header = sign(compact)

    tampered = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=pretty.encode(),
        headers={"Stripe-Signature": header},
    )
    assert tampered.status_code == 400
    assert _event_rows(db_session) == []

    exact = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=compact.encode(),
        headers={"Stripe-Signature": header},
    )
    assert exact.status_code == 200


def test_malformed_json_rejected(client, db_session, stripe_integration_id):
    response = post_signed(client, stripe_integration_id, '{"id": "evt_bad", "type": ')
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid webhook payload"}
    assert _event_rows(db_session) == []


def test_non_object_json_rejected(client, db_session, stripe_integration_id):
    response = post_signed(client, stripe_integration_id, "[1, 2, 3]")
    assert response.status_code == 400
    assert _event_rows(db_session) == []


def test_missing_event_id_rejected(client, db_session, stripe_integration_id):
    event = make_event()
    del event["id"]
    response = post_event(client, stripe_integration_id, event)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid webhook payload"}
    assert _event_rows(db_session) == []


def test_missing_secret_returns_503(client, db_session, stripe_integration_id, monkeypatch):
    monkeypatch.setattr(
        receiver_module, "get_settings", lambda: SimpleNamespace(stripe_webhook_secret=None)
    )
    response = post_event(client, stripe_integration_id, make_event())
    assert response.status_code == 503
    assert response.json() == {"detail": "Stripe webhook verification not configured"}
    assert _event_rows(db_session) == []


def test_unknown_integration_returns_404(client):
    response = post_event(client, "00000000-0000-0000-0000-000000000000", make_event())
    assert response.status_code == 404


def test_github_integration_rejected(client, db_session, github_integration_id):
    response = post_event(client, github_integration_id, make_event())
    assert response.status_code == 400
    assert response.json() == {"detail": "Integration provider must be stripe"}
    assert _event_rows(db_session) == []


def test_duplicate_delivery_is_counted_not_duplicated(client, db_session, stripe_integration_id):
    first = post_event(client, stripe_integration_id, make_event())
    second = post_event(client, stripe_integration_id, make_event())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json() == {"received": True, "duplicate": True, "event_id": "evt_test_1"}

    rows = _event_rows(db_session)
    assert len(rows) == 1
    assert rows[0].delivery_count == 2
    assert rows[0].last_received_at >= rows[0].first_received_at


def test_different_event_ids_are_separate_rows(client, db_session, stripe_integration_id):
    post_event(client, stripe_integration_id, make_event(event_id="evt_a"))
    post_event(client, stripe_integration_id, make_event(event_id="evt_b"))
    assert len(_event_rows(db_session)) == 2


def test_sensitive_payload_fields_are_not_stored_or_exposed(client, db_session, stripe_integration_id):
    event = make_event(
        extra_object={
            "customer": {"id": "cus_test_1", "email": "person@example.com"},
            "receipt_email": "person@example.com",
            "payment_method_details": {"card": {"last4": "4242", "exp_month": 12}},
            "client_secret": "pi_test_1_secret_do_not_store",
        }
    )
    assert post_event(client, stripe_integration_id, event).status_code == 200

    event_row = _event_rows(db_session)[0]
    detail = client.get(f"/api/webhooks/stripe/events/{event_row.id}").text
    listing = client.get("/api/webhooks/stripe/events").text
    stored = json.dumps({c.name: str(getattr(event_row, c.name)) for c in WebhookEventORM.__table__.columns})
    for blob in (detail, listing, stored):
        for forbidden in ("person@example.com", "4242", "cus_test_1", "secret_do_not_store", "whsec_"):
            assert forbidden not in blob


def test_inbound_webhooks_not_written_to_provider_request_logs(client, db_session, stripe_integration_id):
    post_event(client, stripe_integration_id, make_event())
    db_session.expire_all()
    assert db_session.scalar(select(func.count(ProviderRequestLogORM.id))) == 0


def test_delivery_success_is_independent_of_processing_failure(
    client, db_session, stripe_integration_id
):
    """An event whose processing will fail permanently is still acknowledged with 2xx."""
    response = post_event(client, stripe_integration_id, make_event(object_id=None))
    assert response.status_code == 200

    tick = client.post("/api/webhooks/stripe/process-due")
    assert tick.status_code == 200
    assert tick.json()["failed"] == 1

    # Stripe redelivering the same event is still a 2xx duplicate, not an error.
    again = post_event(client, stripe_integration_id, make_event(object_id=None))
    assert again.status_code == 200
    assert again.json()["duplicate"] is True
    row = _event_rows(db_session)[0]
    assert row.processing_status == "failed"
    assert row.delivery_count == 2
