"""Phase B: handler dispatch, retries, failed queue, and effect idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app.db.models.webhook import WebhookEffectORM, WebhookEventORM
from app.repositories.webhooks import (
    webhook_attempt_repository,
    webhook_effect_repository,
    webhook_event_repository,
)
from app.services.webhook_handlers import (
    EffectSpec,
    PermanentWebhookError,
    RetryableWebhookError,
    build_default_registry,
    build_effect_key,
)
from app.services.webhook_processor import ProcessOutcome, StripeWebhookProcessor
from tests.stripe_helpers import make_event, post_event, store_event

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _effects(session, event_id) -> list[WebhookEffectORM]:
    session.expire_all()
    return webhook_effect_repository.list_for_event(session, event_id)


def _reload(session, event_id) -> WebhookEventORM:
    session.expire_all()
    return webhook_event_repository.get(session, event_id)


def _registry_with(event_type: str, handler):
    registry = build_default_registry()
    registry.register(event_type, handler)
    return registry


@pytest.mark.parametrize(
    ("event_type", "effect_type"),
    [
        ("payment_intent.succeeded", "payment_success_recorded"),
        ("payment_intent.payment_failed", "payment_failure_recorded"),
        ("charge.refunded", "refund_recorded"),
    ],
)
def test_supported_handlers_record_one_effect(db_session, stripe_integration_id, event_type, effect_type):
    event = store_event(db_session, stripe_integration_id, event_type=event_type, now=T0)

    result = StripeWebhookProcessor().process_event(db_session, event.id, now=T0)

    assert result.outcome == ProcessOutcome.PROCESSED
    row = _reload(db_session, event.id)
    assert row.processing_status == "processed"
    assert row.processed_at == T0
    assert row.attempt_count == 1
    effects = _effects(db_session, event.id)
    assert [e.effect_type for e in effects] == [effect_type]
    assert effects[0].effect_key == build_effect_key(row, effect_type)
    attempts = webhook_attempt_repository.list_for_event(db_session, event.id)
    assert [a.outcome for a in attempts] == ["succeeded"]


def test_unknown_event_type_is_ignored(db_session, stripe_integration_id):
    event = store_event(db_session, stripe_integration_id, event_type="customer.created", now=T0)

    result = StripeWebhookProcessor().process_event(db_session, event.id, now=T0)

    assert result.outcome == ProcessOutcome.IGNORED
    assert _reload(db_session, event.id).processing_status == "ignored"
    assert _effects(db_session, event.id) == []


def test_unknown_event_type_via_http_is_2xx_and_ignored(client, db_session, stripe_integration_id):
    response = post_event(client, stripe_integration_id, make_event("invoice.created"))
    assert response.status_code == 200
    counts = client.post("/api/webhooks/stripe/process-due").json()
    assert counts["ignored"] == 1


def test_missing_object_id_is_permanent_single_attempt(db_session, stripe_integration_id):
    event = store_event(db_session, stripe_integration_id, object_id=None, now=T0)

    result = StripeWebhookProcessor().process_event(db_session, event.id, now=T0)

    assert result.outcome == ProcessOutcome.FAILED
    row = _reload(db_session, event.id)
    assert row.processing_status == "failed"
    assert row.failed_at == T0
    assert row.attempt_count == 1
    assert row.last_error_code == "webhook_invalid_event_data"
    attempts = webhook_attempt_repository.list_for_event(db_session, event.id)
    assert len(attempts) == 1
    assert attempts[0].retryable is False
    assert attempts[0].scheduled_delay_seconds is None


def test_retryable_failures_back_off_then_succeed(db_session, stripe_integration_id):
    calls = {"n": 0}

    def flaky(event):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RetryableWebhookError("webhook_handler_temporary_failure", "Temporary failure.")
        return EffectSpec("payment_success_recorded", "ok")

    processor = StripeWebhookProcessor(registry=_registry_with("payment_intent.succeeded", flaky))
    event = store_event(db_session, stripe_integration_id, now=T0)

    first = processor.process_due(db_session, now=T0)
    assert first.retry_scheduled == 1
    row = _reload(db_session, event.id)
    assert row.processing_status == "retry_scheduled"
    assert row.next_attempt_at == T0 + timedelta(seconds=1)

    # Not due yet — nothing happens and no attempt is consumed.
    early = processor.process_due(db_session, now=T0 + timedelta(milliseconds=500))
    assert early.model_dump() == {"processed": 0, "retry_scheduled": 0, "failed": 0, "ignored": 0, "skipped": 0}

    second = processor.process_due(db_session, now=T0 + timedelta(seconds=1))
    assert second.retry_scheduled == 1
    assert _reload(db_session, event.id).next_attempt_at == T0 + timedelta(seconds=3)

    third = processor.process_due(db_session, now=T0 + timedelta(seconds=3))
    assert third.processed == 1

    row = _reload(db_session, event.id)
    assert row.processing_status == "processed"
    assert row.last_error_code is None
    attempts = webhook_attempt_repository.list_for_event(db_session, event.id)
    assert [a.outcome for a in attempts] == ["failed", "failed", "succeeded"]
    assert [a.scheduled_delay_seconds for a in attempts] == [1, 2, None]
    assert len(_effects(db_session, event.id)) == 1


def test_exhausted_retries_move_to_failed_queue(db_session, stripe_integration_id):
    def always_down(event):
        raise RetryableWebhookError("webhook_handler_temporary_failure", "Temporary failure.")

    processor = StripeWebhookProcessor(registry=_registry_with("payment_intent.succeeded", always_down))
    event = store_event(db_session, stripe_integration_id, now=T0)

    now = T0
    outcomes = []
    for _ in range(4):
        outcomes.append(processor.process_event(db_session, event.id, now=now).outcome)
        row = _reload(db_session, event.id)
        if row.next_attempt_at:
            now = row.next_attempt_at

    assert outcomes == [ProcessOutcome.RETRY_SCHEDULED] * 3 + [ProcessOutcome.FAILED]
    row = _reload(db_session, event.id)
    assert row.processing_status == "failed"
    assert row.failed_at is not None
    assert row.next_attempt_at is None
    assert row.attempt_count == 4
    assert row.last_error_code == "webhook_handler_temporary_failure"
    attempts = webhook_attempt_repository.list_for_event(db_session, event.id)
    assert [a.scheduled_delay_seconds for a in attempts] == [1, 2, 4, None]
    assert _effects(db_session, event.id) == []

    later = processor.process_due(db_session, now=now + timedelta(hours=1))
    assert later.model_dump()["failed"] == 0
    assert _reload(db_session, event.id).attempt_count == 4


def test_unexpected_exception_is_classified_and_retried(db_session, stripe_integration_id):
    def boom(event):
        raise RuntimeError("database password is hunter2")

    processor = StripeWebhookProcessor(registry=_registry_with("payment_intent.succeeded", boom))
    event = store_event(db_session, stripe_integration_id, now=T0)

    result = processor.process_event(db_session, event.id, now=T0)

    assert result.outcome == ProcessOutcome.RETRY_SCHEDULED
    row = _reload(db_session, event.id)
    assert row.last_error_code == "webhook_processing_error"
    assert "hunter2" not in (row.last_error_message or "")


def test_permanent_handler_error_fails_immediately(db_session, stripe_integration_id):
    def reject(event):
        raise PermanentWebhookError("webhook_invalid_event_data", "Bad data.")

    processor = StripeWebhookProcessor(registry=_registry_with("payment_intent.succeeded", reject))
    event = store_event(db_session, stripe_integration_id, now=T0)

    assert processor.process_event(db_session, event.id, now=T0).outcome == ProcessOutcome.FAILED
    assert _reload(db_session, event.id).attempt_count == 1


def test_reprocessing_and_redelivery_do_not_duplicate_effects(client, db_session, stripe_integration_id):
    post_event(client, stripe_integration_id, make_event())
    event_id = db_session.scalar(select(WebhookEventORM.id))
    processor = StripeWebhookProcessor()

    assert processor.process_event(db_session, event_id).outcome == ProcessOutcome.PROCESSED
    # Processed events are not claimable again.
    assert processor.process_event(db_session, event_id).outcome == ProcessOutcome.SKIPPED

    # Stripe redelivers: delivery_count grows, status/effects unchanged.
    assert post_event(client, stripe_integration_id, make_event()).json()["duplicate"] is True
    assert processor.process_due(db_session).processed == 0

    row = _reload(db_session, event_id)
    assert row.delivery_count == 2
    assert row.processing_status == "processed"
    assert len(_effects(db_session, event_id)) == 1


def test_crash_after_effect_before_status_update_is_safe(db_session, stripe_integration_id):
    """Effect exists but status still pending (simulated crash window)."""
    event = store_event(db_session, stripe_integration_id, now=T0)
    webhook_effect_repository.apply_once(
        db_session,
        event_id=event.id,
        effect_key=build_effect_key(event, "payment_success_recorded"),
        effect_type="payment_success_recorded",
        provider_object_id="pi_test_1",
        summary="applied before crash",
        applied_at=T0,
    )
    db_session.commit()

    result = StripeWebhookProcessor().process_event(db_session, event.id, now=T0 + timedelta(seconds=5))

    assert result.outcome == ProcessOutcome.PROCESSED
    effects = _effects(db_session, event.id)
    assert len(effects) == 1
    assert effects[0].summary == "applied before crash"


def test_stale_processing_is_recovered(db_session, stripe_integration_id):
    event = store_event(db_session, stripe_integration_id, now=T0)
    processor = StripeWebhookProcessor()
    # Simulate a worker that claimed the event and then died.
    claimed = processor._claim(db_session, event.id, now=T0, manual=False)
    assert isinstance(claimed, tuple)
    assert _reload(db_session, event.id).processing_status == "processing"

    # Still fresh: not reclaimed.
    fresh = processor.process_due(db_session, now=T0 + timedelta(minutes=1))
    assert fresh.processed == 0

    recovered = processor.process_due(db_session, now=T0 + timedelta(minutes=10))
    assert recovered.processed == 1

    attempts = webhook_attempt_repository.list_for_event(db_session, event.id)
    assert [a.outcome for a in attempts] == ["abandoned", "succeeded"]
    assert attempts[0].error_code == "webhook_processing_abandoned"
    assert len(_effects(db_session, event.id)) == 1


def test_stale_processing_with_exhausted_budget_fails(db_session, stripe_integration_id):
    event = store_event(db_session, stripe_integration_id, now=T0)
    db_session.execute(
        text(
            "UPDATE webhook_events SET processing_status='processing', "
            "processing_started_at=:started, attempt_count=4, cycle_attempt_count=4 WHERE id=:id"
        ),
        {"started": T0, "id": event.id},
    )
    db_session.commit()

    counts = StripeWebhookProcessor().process_due(db_session, now=T0 + timedelta(minutes=10))

    assert counts.failed == 1
    row = _reload(db_session, event.id)
    assert row.processing_status == "failed"
    assert row.last_error_code == "webhook_processing_abandoned"


def test_event_ordering_is_not_assumed(db_session, stripe_integration_id):
    """A refund can arrive before the payment success; each is handled independently."""
    refund = store_event(
        db_session, stripe_integration_id, event_type="charge.refunded",
        event_id="evt_refund", object_id="ch_1", now=T0,
    )
    success = store_event(
        db_session, stripe_integration_id, event_type="payment_intent.succeeded",
        event_id="evt_success", object_id="pi_1", now=T0 + timedelta(seconds=1),
    )

    counts = StripeWebhookProcessor().process_due(db_session, now=T0 + timedelta(seconds=2))

    assert counts.processed == 2
    assert _reload(db_session, refund.id).processing_status == "processed"
    assert _reload(db_session, success.id).processing_status == "processed"


def test_locked_event_is_skipped(db_session, TestingSessionLocal, stripe_integration_id):
    event = store_event(db_session, stripe_integration_id, now=T0)
    other = TestingSessionLocal()
    try:
        webhook_event_repository.lock_for_update(other, event.id)
        result = StripeWebhookProcessor().process_event(db_session, event.id, now=T0)
        assert result.outcome == ProcessOutcome.SKIPPED
    finally:
        other.rollback()
        other.close()
    assert _reload(db_session, event.id).attempt_count == 0


def test_process_due_respects_limit(db_session, stripe_integration_id):
    for i in range(3):
        store_event(db_session, stripe_integration_id, event_id=f"evt_{i}", now=T0)

    counts = StripeWebhookProcessor().process_due(db_session, limit=2, now=T0)

    assert counts.processed == 2
    db_session.expire_all()
    pending = db_session.scalar(
        select(func.count(WebhookEventORM.id)).where(WebhookEventORM.processing_status == "pending")
    )
    assert pending == 1
