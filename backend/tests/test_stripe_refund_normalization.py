"""Normalization semantics for charge.refunded amounts."""

from __future__ import annotations

from app.services.stripe_webhooks import normalize_stripe_event
from tests.stripe_helpers import make_event, post_event


def test_charge_refunded_uses_per_event_delta() -> None:
    event = make_event(
        "charge.refunded",
        object_id="ch_1",
        extra_object={
            "object": "charge",
            "amount_refunded": 2000,
            "amount": 5000,
        },
    )
    event["data"]["previous_attributes"] = {"amount_refunded": 1000}

    normalized = normalize_stripe_event(event)

    assert normalized.amount == 1000


def test_charge_refunded_without_previous_attributes_has_no_amount() -> None:
    event = make_event(
        "charge.refunded",
        object_id="ch_1",
        extra_object={"object": "charge", "amount_refunded": 2000},
    )

    normalized = normalize_stripe_event(event)

    assert normalized.amount is None


def test_two_partial_refunds_store_per_event_amounts(
    client, db_session, stripe_integration_id
) -> None:
    first = make_event(
        "charge.refunded",
        event_id="evt_refund_1",
        object_id="ch_shared",
        extra_object={"object": "charge", "amount_refunded": 1000},
    )
    first["data"]["previous_attributes"] = {"amount_refunded": 0}
    second = make_event(
        "charge.refunded",
        event_id="evt_refund_2",
        object_id="ch_shared",
        extra_object={"object": "charge", "amount_refunded": 2000},
    )
    second["data"]["previous_attributes"] = {"amount_refunded": 1000}

    assert post_event(client, stripe_integration_id, first).status_code == 200
    assert post_event(client, stripe_integration_id, second).status_code == 200

    db_session.expire_all()
    from sqlalchemy import select

    from app.db.models.webhook import WebhookEventORM

    rows = list(
        db_session.scalars(
            select(WebhookEventORM).order_by(WebhookEventORM.provider_event_id)
        ).all()
    )
    assert [row.amount for row in rows] == [1000, 1000]

    from app.repositories.webhooks import webhook_effect_repository
    from app.services.webhook_processor import StripeWebhookProcessor

    StripeWebhookProcessor().process_due(db_session)

    effects_1 = webhook_effect_repository.list_for_event(db_session, rows[0].id)
    effects_2 = webhook_effect_repository.list_for_event(db_session, rows[1].id)
    assert "10.00 USD" in effects_1[0].summary
    assert "10.00 USD" in effects_2[0].summary
    assert "20.00 USD" not in effects_2[0].summary
