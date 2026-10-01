"""ORM models for support cases, notes, evidence pins, history, and operator audit."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportCaseORM(Base):
    """First-class operational investigation case (not a log row)."""

    __tablename__ = "support_cases"
    __table_args__ = (UniqueConstraint("case_number", name="uq_support_cases_case_number"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_number: Mapped[str] = mapped_column(String(32), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    impact_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspected_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitigation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monitoring_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SupportCaseHistoryORM(Base):
    """Immutable case lifecycle / field-change history."""

    __tablename__ = "support_case_history"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    support_case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SupportCaseNoteORM(Base):
    """Operator note / update on a support case."""

    __tablename__ = "support_case_notes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    support_case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SupportCaseEvidenceORM(Base):
    """Pinned reference to durable evidence (not a full row copy)."""

    __tablename__ = "support_case_evidence"
    __table_args__ = (
        UniqueConstraint(
            "support_case_id",
            "evidence_type",
            "evidence_id",
            name="uq_support_case_evidence_ref",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    support_case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    safe_label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    pinned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OperatorAuditEventORM(Base):
    """Append-oriented operator action audit (not application debug logs)."""

    __tablename__ = "operator_audit_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    integration_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    support_case_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="operator")
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    safe_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
