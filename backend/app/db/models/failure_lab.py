"""ORM models for Failure Lab runs and simulated request metadata."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FailureLabRunORM(Base):
    """Persisted Failure Lab experiment (simulated evidence + diagnosis)."""

    __tablename__ = "failure_lab_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnosis_code: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_title: Mapped[str] = mapped_column(String(120), nullable=False)
    diagnosis_summary: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_checks: Mapped[str | None] = mapped_column(Text, nullable=True)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
