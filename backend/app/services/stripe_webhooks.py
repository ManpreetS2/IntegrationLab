"""Phase A — Stripe webhook RECEIPT.

raw body -> official signature verification -> safe normalization -> durable
receipt/dedupe -> quick acknowledgement. No business processing happens here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import stripe
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.integration import IntegrationProvider
from app.models.webhook import WebhookReceiptResponse
from app.repositories.integrations import integration_repository
from app.repositories.webhooks import NormalizedWebhookEvent, webhook_event_repository
from app.services.webhook_retry import webhook_retry_policy

logger = logging.getLogger(__name__)

PROVIDER = IntegrationProvider.STRIPE.value


def _str_or_none(value: Any, max_len: int = 255) -> str | None:
    if isinstance(value, str) and value:
        return value[:max_len]
    return None


def normalize_stripe_event(event: dict[str, Any]) -> NormalizedWebhookEvent:
    """Keep only safe, useful fields. Raises ValueError if id/type are missing.

    Never retains customer, payment method, card, or email data.
    """
    event_id = _str_or_none(event.get("id"))
    event_type = _str_or_none(event.get("type"))
    if not event_id or not event_type:
        raise ValueError("event id/type missing")

    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    obj = obj if isinstance(obj, dict) else {}

    amount_value = obj.get("amount")
    if event_type == "charge.refunded" and isinstance(obj.get("amount_refunded"), int):
        amount_value = obj.get("amount_refunded")
    amount = amount_value if isinstance(amount_value, int) and not isinstance(amount_value, bool) else None

    created = event.get("created")
    created_at = (
        datetime.fromtimestamp(created, tz=timezone.utc)
        if isinstance(created, int) and not isinstance(created, bool)
        else None
    )
    livemode = event.get("livemode")

    return NormalizedWebhookEvent(
        provider_event_id=event_id,
        event_type=event_type,
        provider_object_id=_str_or_none(obj.get("id")),
        api_version=_str_or_none(event.get("api_version"), 50),
        livemode=livemode if isinstance(livemode, bool) else None,
        provider_created_at=created_at,
        amount=amount,
        currency=_str_or_none(obj.get("currency"), 10),
    )


class StripeWebhookReceiver:
    def receive(
        self,
        session: Session,
        *,
        integration_id: UUID,
        payload: bytes,
        signature_header: str | None,
        now: datetime | None = None,
    ) -> WebhookReceiptResponse:
        integration = integration_repository.get_by_id(session, integration_id)
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        if integration.provider != PROVIDER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Integration provider must be stripe",
            )

        secret = get_settings().stripe_webhook_secret
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe webhook verification not configured",
            )
        if not signature_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Stripe-Signature header",
            )

        try:
            # Exact raw bytes go to the official verifier (default 300s tolerance).
            verified = stripe.Webhook.construct_event(payload, signature_header, secret)
        except stripe.SignatureVerificationError:
            logger.warning("Rejected Stripe webhook with invalid signature for %s", integration_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            ) from None
        except (ValueError, TypeError, AttributeError, KeyError):
            logger.warning("Rejected Stripe webhook with invalid payload for %s", integration_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload",
            ) from None

        try:
            normalized = normalize_stripe_event(verified.to_dict())
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload",
            ) from None

        received_at = now or datetime.now(timezone.utc)
        try:
            result = webhook_event_repository.record_receipt(
                session,
                integration_id=integration.id,
                provider=PROVIDER,
                event=normalized,
                max_attempts=webhook_retry_policy.max_attempts,
                now=received_at,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to store Stripe webhook receipt")
            # Not durably stored: a 5xx lets Stripe redeliver later.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store webhook",
            ) from None

        logger.info(
            "Stripe webhook %s (%s) received for integration %s duplicate=%s",
            normalized.provider_event_id,
            normalized.event_type,
            integration.id,
            result.duplicate,
        )
        return WebhookReceiptResponse(
            received=True,
            duplicate=result.duplicate,
            event_id=normalized.provider_event_id,
        )


stripe_webhook_receiver = StripeWebhookReceiver()
