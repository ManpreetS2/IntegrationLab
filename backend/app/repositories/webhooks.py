"""Repositories for webhook events, processing attempts, and effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models.webhook import (
    WebhookEffectORM,
    WebhookEventORM,
    WebhookProcessingAttemptORM,
)
from app.models.webhook import WebhookProcessingStatus


@dataclass(frozen=True)
class NormalizedWebhookEvent:
    """Safe subset of a verified provider event (no raw payload)."""

    provider_event_id: str
    event_type: str
    provider_object_id: str | None
    api_version: str | None
    livemode: bool | None
    provider_created_at: datetime | None
    amount: int | None
    currency: str | None


@dataclass(frozen=True)
class ReceiptResult:
    event_id: UUID
    duplicate: bool


class WebhookEventRepository:
    def record_receipt(
        self,
        session: Session,
        *,
        integration_id: UUID,
        provider: str,
        event: NormalizedWebhookEvent,
        max_attempts: int,
        now: datetime,
    ) -> ReceiptResult:
        """Insert a new logical event, or count a duplicate delivery.

        Race-safe: concurrent deliveries of the same event id hit the unique
        constraint; the loser increments delivery_count atomically instead.
        """
        insert_stmt = (
            pg_insert(WebhookEventORM)
            .values(
                id=uuid4(),
                integration_id=integration_id,
                provider=provider,
                provider_event_id=event.provider_event_id,
                event_type=event.event_type,
                provider_object_id=event.provider_object_id,
                api_version=event.api_version,
                livemode=event.livemode,
                provider_created_at=event.provider_created_at,
                amount=event.amount,
                currency=event.currency,
                processing_status=WebhookProcessingStatus.PENDING.value,
                delivery_count=1,
                attempt_count=0,
                cycle_attempt_count=0,
                retry_cycle=1,
                manual_retry_count=0,
                max_attempts=max_attempts,
                next_attempt_at=now,
                first_received_at=now,
                last_received_at=now,
            )
            .on_conflict_do_nothing(
                constraint="uq_webhook_events_integration_provider_event",
            )
            .returning(WebhookEventORM.id)
        )
        inserted_id = session.execute(insert_stmt).scalar_one_or_none()
        if inserted_id is not None:
            return ReceiptResult(event_id=inserted_id, duplicate=False)

        duplicate_id = session.execute(
            update(WebhookEventORM)
            .where(
                WebhookEventORM.integration_id == integration_id,
                WebhookEventORM.provider == provider,
                WebhookEventORM.provider_event_id == event.provider_event_id,
            )
            .values(
                delivery_count=WebhookEventORM.delivery_count + 1,
                last_received_at=now,
            )
            .returning(WebhookEventORM.id)
        ).scalar_one()
        return ReceiptResult(event_id=duplicate_id, duplicate=True)

    def get(self, session: Session, event_id: UUID) -> WebhookEventORM | None:
        return session.get(WebhookEventORM, event_id)

    def lock_for_update(
        self,
        session: Session,
        event_id: UUID,
        *,
        skip_locked: bool = False,
    ) -> WebhookEventORM | None:
        """SELECT ... FOR UPDATE [SKIP LOCKED] on one event row."""
        statement = (
            select(WebhookEventORM)
            .where(WebhookEventORM.id == event_id)
            .with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True)
        )
        return session.scalars(statement).first()

    def list_events(
        self,
        session: Session,
        *,
        status: str | None = None,
        event_type: str | None = None,
        integration_id: UUID | None = None,
        limit: int = 50,
    ) -> list[WebhookEventORM]:
        statement = select(WebhookEventORM).order_by(
            WebhookEventORM.first_received_at.desc(),
            WebhookEventORM.id.desc(),
        )
        if status:
            statement = statement.where(WebhookEventORM.processing_status == status)
        if event_type:
            statement = statement.where(WebhookEventORM.event_type == event_type)
        if integration_id is not None:
            statement = statement.where(WebhookEventORM.integration_id == integration_id)
        return list(session.scalars(statement.limit(limit)).all())

    def list_failed(self, session: Session, *, limit: int = 50) -> list[WebhookEventORM]:
        statement = (
            select(WebhookEventORM)
            .where(WebhookEventORM.processing_status == WebhookProcessingStatus.FAILED.value)
            .order_by(WebhookEventORM.failed_at.desc().nulls_last())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def list_due_ids(
        self,
        session: Session,
        *,
        now: datetime,
        stale_after: timedelta,
        limit: int,
    ) -> list[UUID]:
        """Ids that a worker tick should try to claim (claiming re-checks under lock)."""
        statement = (
            select(WebhookEventORM.id)
            .where(
                or_(
                    WebhookEventORM.processing_status == WebhookProcessingStatus.PENDING.value,
                    (
                        (WebhookEventORM.processing_status
                         == WebhookProcessingStatus.RETRY_SCHEDULED.value)
                        & (WebhookEventORM.next_attempt_at <= now)
                    ),
                    (
                        (WebhookEventORM.processing_status
                         == WebhookProcessingStatus.PROCESSING.value)
                        & (WebhookEventORM.processing_started_at < now - stale_after)
                    ),
                )
            )
            .order_by(
                func.coalesce(
                    WebhookEventORM.next_attempt_at,
                    WebhookEventORM.first_received_at,
                ).asc()
            )
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def status_counts(self, session: Session) -> dict[str, int]:
        rows = session.execute(
            select(WebhookEventORM.processing_status, func.count()).group_by(
                WebhookEventORM.processing_status
            )
        ).all()
        return {status: count for status, count in rows}

    def total_and_duplicates(self, session: Session) -> tuple[int, int]:
        total, duplicates = session.execute(
            select(
                func.count(WebhookEventORM.id),
                func.coalesce(func.sum(WebhookEventORM.delivery_count - 1), 0),
            )
        ).one()
        return int(total), int(duplicates)


class WebhookAttemptRepository:
    def create(
        self,
        session: Session,
        *,
        event: WebhookEventORM,
        started_at: datetime,
        manual: bool,
    ) -> WebhookProcessingAttemptORM:
        attempt = WebhookProcessingAttemptORM(
            id=uuid4(),
            webhook_event_id=event.id,
            attempt_number=event.attempt_count,
            retry_cycle=event.retry_cycle,
            cycle_attempt_number=event.cycle_attempt_count,
            started_at=started_at,
            outcome="in_progress",
            manual=manual,
        )
        session.add(attempt)
        session.flush()
        return attempt

    def get(self, session: Session, attempt_id: UUID) -> WebhookProcessingAttemptORM | None:
        return session.get(WebhookProcessingAttemptORM, attempt_id)

    def list_for_event(
        self, session: Session, event_id: UUID
    ) -> list[WebhookProcessingAttemptORM]:
        statement = (
            select(WebhookProcessingAttemptORM)
            .where(WebhookProcessingAttemptORM.webhook_event_id == event_id)
            .order_by(WebhookProcessingAttemptORM.attempt_number.asc())
        )
        return list(session.scalars(statement).all())

    def close_open_attempts(
        self,
        session: Session,
        *,
        event_id: UUID,
        finished_at: datetime,
    ) -> int:
        """Mark attempts left in_progress by a crashed worker as abandoned."""
        result = session.execute(
            update(WebhookProcessingAttemptORM)
            .where(
                WebhookProcessingAttemptORM.webhook_event_id == event_id,
                WebhookProcessingAttemptORM.outcome == "in_progress",
            )
            .values(
                outcome="abandoned",
                finished_at=finished_at,
                error_code="webhook_processing_abandoned",
                error_message="Processing did not finish (worker stopped or crashed).",
                retryable=True,
            )
        )
        return result.rowcount or 0


class WebhookEffectRepository:
    def apply_once(
        self,
        session: Session,
        *,
        event_id: UUID,
        effect_key: str,
        effect_type: str,
        provider_object_id: str | None,
        summary: str | None,
        applied_at: datetime,
    ) -> bool:
        """INSERT ... ON CONFLICT DO NOTHING. Returns True only if newly applied."""
        statement = (
            pg_insert(WebhookEffectORM)
            .values(
                id=uuid4(),
                webhook_event_id=event_id,
                effect_key=effect_key,
                effect_type=effect_type,
                provider_object_id=provider_object_id,
                summary=summary,
                applied_at=applied_at,
            )
            .on_conflict_do_nothing(constraint="uq_webhook_effects_event_effect_key")
            .returning(WebhookEffectORM.id)
        )
        return session.execute(statement).scalar_one_or_none() is not None

    def list_for_event(self, session: Session, event_id: UUID) -> list[WebhookEffectORM]:
        statement = (
            select(WebhookEffectORM)
            .where(WebhookEffectORM.webhook_event_id == event_id)
            .order_by(WebhookEffectORM.applied_at.asc())
        )
        return list(session.scalars(statement).all())


webhook_event_repository = WebhookEventRepository()
webhook_attempt_repository = WebhookAttemptRepository()
webhook_effect_repository = WebhookEffectRepository()
