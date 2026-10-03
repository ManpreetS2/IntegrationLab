"""Operator-facing webhook queries and actions (list, detail, retry, dismiss)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.correlation import short_entity_id
from app.db.models.webhook import WebhookEventORM
from app.models.webhook import (
    WebhookAttemptResponse,
    WebhookEffectResponse,
    WebhookEventDetail,
    WebhookEventSummary,
    WebhookProcessingStatus,
    WebhookSummaryResponse,
)
from app.repositories.webhooks import (
    webhook_attempt_repository,
    webhook_effect_repository,
    webhook_event_repository,
)
from app.services.audit import audit_service
from app.services.webhook_processor import (
    ProcessOutcome,
    StripeWebhookProcessor,
    stripe_webhook_processor,
)

PROCESSABLE_NOW = {
    WebhookProcessingStatus.PENDING.value,
    WebhookProcessingStatus.RETRY_SCHEDULED.value,
}
# Choice: the retry endpoint also reopens dismissed events (no separate undismiss).
RETRYABLE_BY_OPERATOR = {
    WebhookProcessingStatus.FAILED.value,
    WebhookProcessingStatus.DISMISSED.value,
}
DISMISSABLE = {
    WebhookProcessingStatus.FAILED.value,
    WebhookProcessingStatus.RETRY_SCHEDULED.value,
}


class WebhookEventService:
    def __init__(self, processor: StripeWebhookProcessor | None = None) -> None:
        self.processor = processor or stripe_webhook_processor

    def summary(self, session: Session) -> WebhookSummaryResponse:
        counts = webhook_event_repository.status_counts(session)
        total, duplicates = webhook_event_repository.total_and_duplicates(session)
        return WebhookSummaryResponse(
            received=total,
            duplicate_deliveries=duplicates,
            **{s.value: counts.get(s.value, 0) for s in WebhookProcessingStatus},
        )

    def list_events(self, session: Session, **filters) -> list[WebhookEventSummary]:
        rows = webhook_event_repository.list_events(session, **filters)
        return [WebhookEventSummary.model_validate(row) for row in rows]

    def list_failed(self, session: Session, *, limit: int) -> list[WebhookEventSummary]:
        rows = webhook_event_repository.list_failed(session, limit=limit)
        return [WebhookEventSummary.model_validate(row) for row in rows]

    def detail(self, session: Session, event_id: UUID) -> WebhookEventDetail:
        event = self._get_or_404(session, event_id)
        effects = webhook_effect_repository.list_for_event(session, event.id)
        attempts = webhook_attempt_repository.list_for_event(session, event.id)
        base = WebhookEventSummary.model_validate(event).model_dump()
        return WebhookEventDetail(
            **base,
            api_version=event.api_version,
            provider_created_at=event.provider_created_at,
            processing_started_at=event.processing_started_at,
            effects=[WebhookEffectResponse.model_validate(e) for e in effects],
            attempts=[WebhookAttemptResponse.model_validate(a) for a in attempts],
        )

    def process_now(self, session: Session, event_id: UUID) -> WebhookEventDetail:
        event = self._get_or_404(session, event_id)
        if event.processing_status == WebhookProcessingStatus.PROCESSING.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Event is already being processed")
        if event.processing_status not in PROCESSABLE_NOW:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Event is {event.processing_status}; use retry to reopen failed events",
            )
        session.rollback()
        result = self.processor.process_event(session, event_id, manual=True)
        if result.outcome == ProcessOutcome.SKIPPED:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Event is already being processed")
        return self.detail(session, event_id)

    def retry(
        self,
        session: Session,
        event_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> WebhookEventDetail:
        """Operator retry: new retry cycle with a fresh budget; history kept."""
        event = webhook_event_repository.lock_for_update(session, event_id)
        if event is None:
            session.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
        if event.processing_status not in RETRYABLE_BY_OPERATOR:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Only failed or dismissed events can be retried (status: {event.processing_status})",
            )
        now = datetime.now(timezone.utc)
        event.processing_status = WebhookProcessingStatus.PENDING.value
        event.manual_retry_count += 1
        event.retry_cycle += 1
        event.cycle_attempt_count = 0
        event.next_attempt_at = now
        event.failed_at = None
        event.dismissed_at = None
        audit_service.record(
            session,
            action="webhook_retry_requested",
            target_type="webhook_event",
            target_id=event.id,
            integration_id=event.integration_id,
            correlation_id=correlation_id,
            safe_summary=f"Retried Stripe webhook event {short_entity_id(event.id)}",
            metadata={
                "webhook_event_id": str(event.id),
                "provider": "stripe",
                "outcome": WebhookProcessingStatus.PENDING.value,
            },
            commit=False,
        )
        session.commit()
        return self.detail(session, event_id)

    def dismiss(
        self,
        session: Session,
        event_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> WebhookEventDetail:
        event = webhook_event_repository.lock_for_update(session, event_id)
        if event is None:
            session.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
        if event.processing_status not in DISMISSABLE:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Only failed or retry-scheduled events can be dismissed (status: {event.processing_status})",
            )
        event.processing_status = WebhookProcessingStatus.DISMISSED.value
        event.dismissed_at = datetime.now(timezone.utc)
        event.next_attempt_at = None
        audit_service.record(
            session,
            action="webhook_dismissed",
            target_type="webhook_event",
            target_id=event.id,
            integration_id=event.integration_id,
            correlation_id=correlation_id,
            safe_summary=f"Dismissed Stripe webhook event {short_entity_id(event.id)}",
            metadata={
                "webhook_event_id": str(event.id),
                "provider": "stripe",
                "outcome": WebhookProcessingStatus.DISMISSED.value,
            },
            commit=False,
        )
        session.commit()
        return self.detail(session, event_id)

    @staticmethod
    def _get_or_404(session: Session, event_id: UUID) -> WebhookEventORM:
        event = webhook_event_repository.get(session, event_id)
        if event is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
        return event


webhook_event_service = WebhookEventService()
