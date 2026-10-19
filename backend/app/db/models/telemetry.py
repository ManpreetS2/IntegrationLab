"""ORM for ingestion credentials and SDK-reported HTTP observations.

Plaintext credentials are never stored. Event idempotency is
(integration_id, event_id). Provenance cannot be upgraded to verified.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_OUTCOME_CHECK = """
(
  status_code IS NULL AND error_category IN ('timeout', 'transport_error')
) OR (
  status_code BETWEEN 200 AND 399 AND error_category IS NULL
) OR (
  status_code = 429 AND error_category = 'rate_limited'
) OR (
  status_code BETWEEN 400 AND 499 AND status_code <> 429
  AND error_category = 'http_client_error'
) OR (
  status_code BETWEEN 500 AND 599 AND error_category = 'http_server_error'
)
"""


class IngestionCredentialORM(Base):
    """Hash of an SDK ingestion credential scoped to one integration."""

    __tablename__ = "ingestion_credentials"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_ingestion_credentials_key_prefix"),
        UniqueConstraint("secret_hash", name="uq_ingestion_credentials_secret_hash"),
        Index("ix_ingestion_credentials_integration_id", "integration_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ingestion_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        revoked = self.revoked_at is not None
        return (
            f"IngestionCredentialORM(id={self.id}, integration_id={self.integration_id}, "
            f"key_prefix={self.key_prefix}, revoked={revoked})"
        )


class TelemetryEventORM(Base):
    """One SDK-reported HTTP outcome. Not an IntegrationLab provider call."""

    __tablename__ = "telemetry_events"
    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "event_id",
            name="uq_telemetry_events_integration_event",
        ),
        CheckConstraint("duration_ms >= 0 AND duration_ms <= 300000", name="ck_telemetry_events_duration"),
        CheckConstraint("kind = 'http_observation'", name="ck_telemetry_events_kind"),
        CheckConstraint("provenance = 'sdk_reported'", name="ck_telemetry_events_provenance"),
        CheckConstraint(
            "method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')",
            name="ck_telemetry_events_method",
        ),
        CheckConstraint(
            "environment IN ('local', 'test', 'staging', 'production')",
            name="ck_telemetry_events_environment",
        ),
        CheckConstraint(_OUTCOME_CHECK, name="ck_telemetry_events_outcome"),
        Index(
            "ix_telemetry_events_latest",
            "integration_id",
            desc("occurred_at"),
            desc("event_id"),
        ),
        Index(
            "ix_telemetry_events_page",
            "integration_id",
            desc("received_at"),
            desc("event_id"),
        ),
        Index(
            "ix_telemetry_events_service",
            "integration_id",
            "service",
            desc("occurred_at"),
        ),
        Index(
            "ix_telemetry_events_category",
            "integration_id",
            "error_category",
            desc("occurred_at"),
        ),
        Index(
            "ix_telemetry_events_status",
            "integration_id",
            "status_code",
            desc("occurred_at"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ingestion_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    service: Mapped[str] = mapped_column(String(63), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route_template: Mapped[str] = mapped_column(String(200), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    sdk_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sdk_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
