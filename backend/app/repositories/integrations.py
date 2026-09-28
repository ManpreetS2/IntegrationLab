"""Database access for integrations.

Routes call this repository instead of writing SQL directly.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.integration import IntegrationORM
from app.models.integration import IntegrationCreate, IntegrationStatus


class IntegrationRepository:
    """Small data-access helper around the integrations table."""

    def list_all(self, session: Session) -> list[IntegrationORM]:
        """Return every integration ordered by creation time."""
        statement = select(IntegrationORM).order_by(IntegrationORM.created_at.asc())
        return list(session.scalars(statement).all())

    def get_by_id(self, session: Session, integration_id: UUID) -> IntegrationORM | None:
        """Fetch one integration by primary key, or None if missing."""
        return session.get(IntegrationORM, integration_id)

    def create(self, session: Session, payload: IntegrationCreate) -> IntegrationORM:
        """Insert a new integration and return the persisted ORM row."""
        record = IntegrationORM(
            id=uuid4(),
            name=payload.name,
            provider=payload.provider.value,
            status=IntegrationStatus.NOT_CONNECTED.value,
            created_at=datetime.now(timezone.utc),
            last_checked_at=None,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record

    def find_seed_by_name_and_provider(
        self,
        session: Session,
        name: str,
        provider: str,
    ) -> IntegrationORM | None:
        """Look up a seed row by exact name + provider (for idempotent seeding)."""
        statement = select(IntegrationORM).where(
            IntegrationORM.name == name,
            IntegrationORM.provider == provider,
        )
        return session.scalars(statement).first()


integration_repository = IntegrationRepository()
