"""Phase B — internal webhook PROCESSING with retries.

Per event:
    1. claim   (txn 1): SELECT ... FOR UPDATE SKIP LOCKED, re-check status,
                        mark `processing`, record an in-progress attempt.
    2. handle  (txn 2): run the handler, INSERT effect ON CONFLICT DO NOTHING,
                        mark `processed` — effect and status commit together.
    3. failure (txn 3): on a classified error, roll back txn 2, close the
                        attempt, and ask the retry policy what happens next.

Stripe's own delivery retries are separate: by the time this runs, the webhook
was already acknowledged with 2xx.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.webhook import WebhookEventORM
from app.models.webhook import (
    AttemptOutcome,
    ProcessDueResponse,
    WebhookProcessingStatus,
)
from app.repositories.webhooks import (
    webhook_attempt_repository,
    webhook_effect_repository,
    webhook_event_repository,
)
from app.services.webhook_handlers import (
    HandlerRegistry,
    WebhookProcessingError,
    build_effect_key,
    default_handler_registry,
)
from app.services.webhook_retry import WebhookRetryPolicy, webhook_retry_policy

logger = logging.getLogger(__name__)

STALE_PROCESSING_AFTER = timedelta(minutes=5)
MAX_BATCH = 50


class ProcessOutcome(str, Enum):
    PROCESSED = "processed"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    IGNORED = "ignored"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ProcessResult:
    event_id: UUID
    outcome: ProcessOutcome


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StripeWebhookProcessor:
    def __init__(
        self,
        registry: HandlerRegistry | None = None,
        retry_policy: WebhookRetryPolicy | None = None,
        stale_after: timedelta = STALE_PROCESSING_AFTER,
    ) -> None:
        self.registry = registry or default_handler_registry
        self.retry_policy = retry_policy or webhook_retry_policy
        self.stale_after = stale_after

    # ---------------------------------------------------------------- public

    def process_event(
        self,
        session: Session,
        event_id: UUID,
        *,
        now: datetime | None = None,
        manual: bool = False,
    ) -> ProcessResult:
        now = now or _utcnow()
        claimed = self._claim(session, event_id, now=now, manual=manual)
        if isinstance(claimed, ProcessResult):
            return claimed
        event, attempt_id = claimed

        handler = self.registry.get(event.event_type)
        if handler is None:
            return self._finish_ignored(session, event_id, attempt_id, now=now)

        try:
            spec = handler(event)
            return self._finish_success(session, event_id, attempt_id, spec, now=now)
        except WebhookProcessingError as exc:
            session.rollback()
            return self._finish_failure(
                session,
                event_id,
                attempt_id,
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                now=now,
            )
        except Exception:
            session.rollback()
            logger.exception("Unexpected error processing webhook event %s", event_id)
            # Unclassified errors get the bounded retry budget; exhaustion lands
            # in the failed queue rather than retrying forever.
            return self._finish_failure(
                session,
                event_id,
                attempt_id,
                code="webhook_processing_error",
                message="Unexpected processing error.",
                retryable=True,
                now=now,
            )

    def process_due(
        self,
        session: Session,
        *,
        limit: int = MAX_BATCH,
        now: datetime | None = None,
    ) -> ProcessDueResponse:
        """One worker tick: process due events once, then return counts."""
        now = now or _utcnow()
        limit = max(1, min(limit, MAX_BATCH))
        due_ids = webhook_event_repository.list_due_ids(
            session, now=now, stale_after=self.stale_after, limit=limit
        )
        session.rollback()

        counts = ProcessDueResponse()
        for event_id in due_ids:
            result = self.process_event(session, event_id, now=now)
            field = result.outcome.value
            setattr(counts, field, getattr(counts, field) + 1)
        return counts

    # --------------------------------------------------------------- phases

    def _claim(
        self,
        session: Session,
        event_id: UUID,
        *,
        now: datetime,
        manual: bool,
    ) -> tuple[WebhookEventORM, UUID] | ProcessResult:
        event = webhook_event_repository.lock_for_update(session, event_id, skip_locked=True)
        if event is None:
            # Missing, or another worker holds the row lock right now.
            session.rollback()
            return ProcessResult(event_id, ProcessOutcome.SKIPPED)

        status = event.processing_status
        reclaiming_stale = False
        if status == WebhookProcessingStatus.PENDING.value:
            claimable = True
        elif status == WebhookProcessingStatus.RETRY_SCHEDULED.value:
            due = event.next_attempt_at is None or event.next_attempt_at <= now
            claimable = manual or due
        elif status == WebhookProcessingStatus.PROCESSING.value:
            started = event.processing_started_at
            reclaiming_stale = started is not None and started < now - self.stale_after
            claimable = reclaiming_stale
        else:
            claimable = False

        if not claimable:
            session.rollback()
            return ProcessResult(event_id, ProcessOutcome.SKIPPED)

        if reclaiming_stale:
            webhook_attempt_repository.close_open_attempts(
                session, event_id=event.id, finished_at=now
            )
            if event.cycle_attempt_count >= event.max_attempts:
                self._mark_failed(
                    event,
                    now=now,
                    code="webhook_processing_abandoned",
                    message="Processing did not finish and the retry budget is exhausted.",
                )
                session.commit()
                return ProcessResult(event_id, ProcessOutcome.FAILED)

        event.processing_status = WebhookProcessingStatus.PROCESSING.value
        event.processing_started_at = now
        event.next_attempt_at = None
        event.attempt_count += 1
        event.cycle_attempt_count += 1
        attempt = webhook_attempt_repository.create(
            session, event=event, started_at=now, manual=manual
        )
        session.commit()
        return event, attempt.id

    def _finish_success(
        self,
        session: Session,
        event_id: UUID,
        attempt_id: UUID,
        spec,
        *,
        now: datetime,
    ) -> ProcessResult:
        event = webhook_event_repository.lock_for_update(session, event_id)
        newly_applied = webhook_effect_repository.apply_once(
            session,
            event_id=event.id,
            effect_key=build_effect_key(event, spec.effect_type),
            effect_type=spec.effect_type,
            provider_object_id=event.provider_object_id,
            summary=spec.summary,
            applied_at=now,
        )
        if not newly_applied:
            logger.info("Effect for webhook event %s already applied; not re-applying", event_id)

        attempt = webhook_attempt_repository.get(session, attempt_id)
        attempt.outcome = AttemptOutcome.SUCCEEDED.value
        attempt.finished_at = now

        event.processing_status = WebhookProcessingStatus.PROCESSED.value
        event.processed_at = now
        event.processing_started_at = None
        event.last_error_code = None
        event.last_error_message = None
        session.commit()
        return ProcessResult(event_id, ProcessOutcome.PROCESSED)

    def _finish_ignored(
        self,
        session: Session,
        event_id: UUID,
        attempt_id: UUID,
        *,
        now: datetime,
    ) -> ProcessResult:
        event = webhook_event_repository.lock_for_update(session, event_id)
        attempt = webhook_attempt_repository.get(session, attempt_id)
        attempt.outcome = AttemptOutcome.IGNORED.value
        attempt.finished_at = now
        event.processing_status = WebhookProcessingStatus.IGNORED.value
        event.processing_started_at = None
        session.commit()
        return ProcessResult(event_id, ProcessOutcome.IGNORED)

    def _finish_failure(
        self,
        session: Session,
        event_id: UUID,
        attempt_id: UUID,
        *,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> ProcessResult:
        event = webhook_event_repository.lock_for_update(session, event_id)
        decision = self.retry_policy.decide(
            failed_attempt_number=event.cycle_attempt_count,
            retryable=retryable,
            now=now,
            max_attempts=event.max_attempts,
        )

        attempt = webhook_attempt_repository.get(session, attempt_id)
        attempt.outcome = AttemptOutcome.FAILED.value
        attempt.finished_at = now
        attempt.error_code = code
        attempt.error_message = message
        attempt.retryable = retryable
        attempt.scheduled_delay_seconds = decision.delay_seconds

        event.processing_started_at = None
        if decision.should_retry:
            event.processing_status = WebhookProcessingStatus.RETRY_SCHEDULED.value
            event.next_attempt_at = decision.next_attempt_at
            event.last_error_code = code
            event.last_error_message = message
            outcome = ProcessOutcome.RETRY_SCHEDULED
        else:
            self._mark_failed(event, now=now, code=code, message=message)
            outcome = ProcessOutcome.FAILED
        session.commit()
        logger.info(
            "Webhook event %s attempt %s failed (%s); outcome=%s",
            event_id,
            event.attempt_count,
            code,
            outcome.value,
        )
        return ProcessResult(event_id, outcome)

    @staticmethod
    def _mark_failed(event: WebhookEventORM, *, now: datetime, code: str, message: str) -> None:
        event.processing_status = WebhookProcessingStatus.FAILED.value
        event.failed_at = now
        event.next_attempt_at = None
        event.processing_started_at = None
        event.last_error_code = code
        event.last_error_message = message


stripe_webhook_processor = StripeWebhookProcessor()
