"""Database access for hashed ingestion credentials."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.telemetry import IngestionCredentialORM


class IngestionCredentialRepository:
    def get(
        self,
        session: Session,
        credential_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionCredentialORM | None:
        if not for_update:
            return session.get(IngestionCredentialORM, credential_id)
        return session.get(IngestionCredentialORM, credential_id, with_for_update=True)

    def get_by_prefix(self, session: Session, key_prefix: str) -> IngestionCredentialORM | None:
        statement = select(IngestionCredentialORM).where(
            IngestionCredentialORM.key_prefix == key_prefix
        )
        return session.scalars(statement).first()

    def list_for_integration(
        self, session: Session, integration_id: UUID
    ) -> list[IngestionCredentialORM]:
        statement = (
            select(IngestionCredentialORM)
            .where(IngestionCredentialORM.integration_id == integration_id)
            .order_by(IngestionCredentialORM.created_at.desc())
        )
        return list(session.scalars(statement).all())

    def count_active(self, session: Session, integration_id: UUID) -> int:
        statement = select(func.count()).select_from(IngestionCredentialORM).where(
            IngestionCredentialORM.integration_id == integration_id,
            IngestionCredentialORM.revoked_at.is_(None),
        )
        return int(session.scalar(statement) or 0)

    def active_counts(self, session: Session) -> dict[UUID, int]:
        statement = (
            select(IngestionCredentialORM.integration_id, func.count())
            .where(IngestionCredentialORM.revoked_at.is_(None))
            .group_by(IngestionCredentialORM.integration_id)
        )
        return {row[0]: int(row[1]) for row in session.execute(statement).all()}

    def add(self, session: Session, record: IngestionCredentialORM) -> IngestionCredentialORM:
        session.add(record)
        session.flush()
        return record


ingestion_credential_repository = IngestionCredentialRepository()
