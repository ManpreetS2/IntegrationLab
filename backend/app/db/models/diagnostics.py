"""ORM models for persisted guided diagnostic runs and their checks."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosticRunORM(Base):
    """One operator-triggered diagnostic run for an integration."""

    __tablename__ = "diagnostic_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # running | pass | warning | fail | unknown
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class DiagnosticCheckORM(Base):
    """One observed check inside a run: evidence + recommendation, never secrets."""

    __tablename__ = "diagnostic_checks"
    __table_args__ = (
        UniqueConstraint(
            "diagnostic_run_id", "check_code", name="uq_diagnostic_checks_run_check_code"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    diagnostic_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("diagnostic_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
