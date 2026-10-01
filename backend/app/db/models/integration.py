"""SQLAlchemy ORM model for the integrations table.

provider and status are stored as plain strings (not Postgres ENUMs)
so future value changes do not require painful ENUM migrations.
Python/Pydantic enums still enforce allowed values at the API layer.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationORM(Base):
    """Database row representing one partner integration."""

    __tablename__ = "integrations"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    # Operational / support metadata (configuration context — not observed health).
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    owner_team: Mapped[str | None] = mapped_column(String(120), nullable=True)
    criticality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    support_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    runbook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    escalation_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    go_live_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_traffic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
