"""Helpers for building locally signed Stripe test events (no network, fake secret)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import stripe
from sqlalchemy.orm import Session

from app.db.models.webhook import WebhookEventORM
from app.repositories.webhooks import NormalizedWebhookEvent, webhook_event_repository

TEST_WEBHOOK_SECRET = "whsec_test_example"


def make_event(
    event_type: str = "payment_intent.succeeded",
    *,
    event_id: str = "evt_test_1",
    object_id: str | None = "pi_test_1",
    amount: int = 2000,
    currency: str = "usd",
    extra_object: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {"object": "payment_intent", "amount": amount, "currency": currency}
    if object_id is not None:
        obj["id"] = object_id
    obj.update(extra_object or {})
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "api_version": "2024-06-20",
        "created": 1_700_000_000,
        "livemode": False,
        "data": {"object": obj},
    }


def sign(payload: str, *, secret: str = TEST_WEBHOOK_SECRET, timestamp: int | None = None) -> str:
    return stripe.WebhookSignature.generate_signature_header(
        payload=payload, secret=secret, timestamp=timestamp
    )


def post_signed(client, integration_id: str | UUID, payload: str, **sign_kwargs):
    return client.post(
        f"/webhooks/stripe/{integration_id}",
        content=payload.encode("utf-8"),
        headers={"Stripe-Signature": sign(payload, **sign_kwargs), "Content-Type": "application/json"},
    )


def post_event(client, integration_id: str | UUID, event: dict[str, Any]):
    return post_signed(client, integration_id, json.dumps(event))


def store_event(
    session: Session,
    integration_id: UUID,
    *,
    event_type: str = "payment_intent.succeeded",
    event_id: str = "evt_test_1",
    object_id: str | None = "pi_test_1",
    now: datetime | None = None,
) -> WebhookEventORM:
    """Record a receipt directly (bypasses HTTP) so tests can control time."""
    result = webhook_event_repository.record_receipt(
        session,
        integration_id=integration_id,
        provider="stripe",
        event=NormalizedWebhookEvent(
            provider_event_id=event_id,
            event_type=event_type,
            provider_object_id=object_id,
            api_version="2024-06-20",
            livemode=False,
            provider_created_at=None,
            amount=2000,
            currency="usd",
        ),
        max_attempts=4,
        now=now or datetime.now(timezone.utc),
    )
    session.commit()
    return webhook_event_repository.get(session, result.event_id)
