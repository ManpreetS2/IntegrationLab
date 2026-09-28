"""ORM models for inbound webhook events, processing attempts, and effects."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEventORM(Base):
    """One logical provider event (deduplicated by provider event id per integration).

    Stores a safe normalized summary only — never the raw request body.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "provider",
            "provider_event_id",
            name="uq_webhook_events_integration_provider_event",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    livemode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Lifetime attempts across every retry cycle (never reset).
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Attempts in the current retry cycle; compared against max_attempts.
    cycle_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Starts at 1; each manual retry opens a new cycle with a fresh retry budget.
    retry_cycle: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    manual_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WebhookProcessingAttemptORM(Base):
    """One processing attempt for a webhook event (history is never deleted)."""

    __tablename__ = "webhook_processing_attempts"
    __table_args__ = (
        UniqueConstraint(
            "webhook_event_id",
            "attempt_number",
            name="uq_webhook_attempts_event_attempt_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    webhook_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("webhook_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    scheduled_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WebhookEffectORM(Base):
    """Internal effect applied by a handler; unique key makes replays harmless."""

    __tablename__ = "webhook_effects"
    __table_args__ = (
        UniqueConstraint(
            "webhook_event_id",
            "effect_key",
            name="uq_webhook_effects_event_effect_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    webhook_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("webhook_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    effect_key: Mapped[str] = mapped_column(String(255), nullable=False)
    effect_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
