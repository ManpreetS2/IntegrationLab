"""Stripe event handlers + registry.

Handlers only produce internal, normalized effects. They never call Stripe,
move money, or create refunds. They read the stored safe summary, not a raw
payload, and do not assume any ordering between event types.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.db.models.webhook import WebhookEventORM


class WebhookProcessingError(Exception):
    """Base for classified processing failures (safe code + concise message)."""

    retryable: bool = False

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RetryableWebhookError(WebhookProcessingError):
    """Temporary condition — safe to try again later."""

    retryable = True


class PermanentWebhookError(WebhookProcessingError):
    """Retrying cannot help (e.g. required business fields missing)."""

    retryable = False


@dataclass(frozen=True)
class EffectSpec:
    effect_type: str
    summary: str


EventHandler = Callable[[WebhookEventORM], EffectSpec]


def build_effect_key(event: WebhookEventORM, effect_type: str) -> str:
    """Deterministic effect identity for one event — replays map to the same key."""
    return f"{event.provider}:{event.provider_event_id}:{effect_type}"


def _require_object_id(event: WebhookEventORM) -> str:
    if not event.provider_object_id:
        raise PermanentWebhookError(
            "webhook_invalid_event_data",
            "Event is missing data.object.id required by this handler.",
        )
    return event.provider_object_id


def _money(event: WebhookEventORM) -> str:
    if event.amount is None or event.currency is None:
        return "amount unavailable"
    return f"{event.amount} {event.currency}"


def handle_payment_intent_succeeded(event: WebhookEventORM) -> EffectSpec:
    object_id = _require_object_id(event)
    return EffectSpec(
        effect_type="payment_success_recorded",
        summary=f"Payment {object_id} succeeded ({_money(event)}).",
    )


def handle_payment_intent_payment_failed(event: WebhookEventORM) -> EffectSpec:
    object_id = _require_object_id(event)
    return EffectSpec(
        effect_type="payment_failure_recorded",
        summary=f"Payment {object_id} failed ({_money(event)}).",
    )


def handle_charge_refunded(event: WebhookEventORM) -> EffectSpec:
    object_id = _require_object_id(event)
    return EffectSpec(
        effect_type="refund_recorded",
        summary=f"Charge {object_id} refunded ({_money(event)}).",
    )


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, EventHandler] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type] = handler

    def get(self, event_type: str) -> EventHandler | None:
        """None means unsupported — the processor marks the event ignored."""
        return self._handlers.get(event_type)

    def supported_types(self) -> list[str]:
        return sorted(self._handlers)


def build_default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register("payment_intent.succeeded", handle_payment_intent_succeeded)
    registry.register("payment_intent.payment_failed", handle_payment_intent_payment_failed)
    registry.register("charge.refunded", handle_charge_refunded)
    return registry


default_handler_registry = build_default_registry()
