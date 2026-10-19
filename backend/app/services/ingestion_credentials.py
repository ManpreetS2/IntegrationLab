"""Create, rotate, revoke, and authenticate ingestion credentials.

The full credential is returned only from create and rotate. Storage keeps a
SHA-256 digest. Authentication compares digests in constant time.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.correlation import short_entity_id
from app.db.models.integration import IntegrationORM
from app.db.models.telemetry import IngestionCredentialORM
from app.models.integration import IntegrationProvider, IntegrationStatus
from app.models.telemetry import (
    IngestionCredentialCreated,
    IngestionCredentialView,
)
from app.repositories.ingestion_credentials import ingestion_credential_repository as repo
from app.repositories.integrations import integration_repository
from app.services.audit import audit_service
from app.services.telemetry_limits import MAX_ACTIVE_CREDENTIALS

_CREDENTIAL_RE = re.compile(r"^ilk_v1_[0-9a-f]{12}_[A-Za-z0-9_-]{43,64}$")
_PREFIX_LENGTH = len("ilk_v1_") + 12
_DUMMY_HASH = hashlib.sha256(b"integrationlab-ingestion-dummy-v1").hexdigest()


@dataclass(frozen=True)
class CredentialAuthentication:
    credential: IngestionCredentialORM | None
    failure: str | None


def hash_credential(credential: str) -> str:
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def _digests_match(stored: str, presented: str) -> bool:
    if len(stored) != len(presented):
        return False
    return secrets.compare_digest(stored, presented)


def parse_credential(credential: str) -> str | None:
    """Return the public key prefix, or None when the format is not v1."""
    if not _CREDENTIAL_RE.fullmatch(credential):
        return None
    return credential[:_PREFIX_LENGTH]


def generate_credential() -> tuple[str, str, str]:
    """Return (full credential, public prefix, sha256 hex)."""
    prefix = f"ilk_v1_{secrets.token_hex(6)}"
    secret = secrets.token_urlsafe(32)
    credential = f"{prefix}_{secret}"
    return credential, prefix, hash_credential(credential)


class IngestionCredentialService:
    def authenticate(self, session: Session, credential: str) -> CredentialAuthentication:
        prefix = parse_credential(credential)
        presented = hash_credential(credential)
        row = repo.get_by_prefix(session, prefix) if prefix else None
        stored = row.secret_hash if row is not None else _DUMMY_HASH
        if not _digests_match(stored, presented) or row is None:
            return CredentialAuthentication(credential=None, failure="invalid")
        if row.revoked_at is not None:
            return CredentialAuthentication(credential=None, failure="revoked")
        return CredentialAuthentication(credential=row, failure=None)

    def create(
        self,
        session: Session,
        integration_id: UUID,
        *,
        label: str | None,
        correlation_id: UUID | None,
    ) -> IngestionCredentialCreated:
        # Lock the integration row so concurrent creates cannot all pass the
        # active-cap check before any insert commits.
        integration = self._require_instrumented(session, integration_id, for_update=True)
        if repo.count_active(session, integration.id) >= MAX_ACTIVE_CREDENTIALS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"At most {MAX_ACTIVE_CREDENTIALS} active ingestion credentials are allowed",
            )
        created = self._insert(session, integration, label=label, rotated_from_id=None)
        self._sync_status(session, integration)
        audit_service.record(
            session,
            action="ingestion_credential_created",
            target_type="ingestion_credential",
            target_id=created.record.id,
            integration_id=integration.id,
            correlation_id=correlation_id,
            safe_summary=(
                f"Created ingestion credential {created.record.key_prefix} "
                f"for integration {short_entity_id(integration.id)}"
            ),
            metadata={
                "provider": integration.provider,
                "credential_id": str(created.record.id),
                "key_prefix": created.record.key_prefix,
                "environment": integration.environment,
            },
            commit=False,
        )
        session.commit()
        session.refresh(created.record)
        return self._created(created.record, created.secret)

    def rotate(
        self,
        session: Session,
        integration_id: UUID,
        credential_id: UUID,
        *,
        label: str | None,
        correlation_id: UUID | None,
    ) -> IngestionCredentialCreated:
        integration = self._require_instrumented(session, integration_id, for_update=True)
        current = self._require_owned(
            session, integration.id, credential_id, for_update=True
        )
        if current.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingestion credential is already revoked",
            )
        created = self._insert(
            session,
            integration,
            label=label if label is not None else current.label,
            rotated_from_id=current.id,
        )
        now = datetime.now(timezone.utc)
        current.revoked_at = now
        session.add(current)
        self._sync_status(session, integration)
        audit_service.record(
            session,
            action="ingestion_credential_rotated",
            target_type="ingestion_credential",
            target_id=created.record.id,
            integration_id=integration.id,
            correlation_id=correlation_id,
            safe_summary=(
                f"Rotated ingestion credential {current.key_prefix} "
                f"to {created.record.key_prefix} for integration {short_entity_id(integration.id)}"
            ),
            metadata={
                "provider": integration.provider,
                "credential_id": str(created.record.id),
                "key_prefix": created.record.key_prefix,
                "rotated_from_id": str(current.id),
                "environment": integration.environment,
            },
            commit=False,
        )
        session.commit()
        session.refresh(created.record)
        return self._created(created.record, created.secret)

    def revoke(
        self,
        session: Session,
        integration_id: UUID,
        credential_id: UUID,
        *,
        correlation_id: UUID | None,
    ) -> IngestionCredentialView:
        integration = self._require_instrumented(session, integration_id, for_update=True)
        current = self._require_owned(
            session, integration.id, credential_id, for_update=True
        )
        if current.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingestion credential is already revoked",
            )
        current.revoked_at = datetime.now(timezone.utc)
        session.add(current)
        self._sync_status(session, integration)
        audit_service.record(
            session,
            action="ingestion_credential_revoked",
            target_type="ingestion_credential",
            target_id=current.id,
            integration_id=integration.id,
            correlation_id=correlation_id,
            safe_summary=(
                f"Revoked ingestion credential {current.key_prefix} "
                f"for integration {short_entity_id(integration.id)}"
            ),
            metadata={
                "provider": integration.provider,
                "credential_id": str(current.id),
                "key_prefix": current.key_prefix,
                "environment": integration.environment,
            },
            commit=False,
        )
        session.commit()
        session.refresh(current)
        return IngestionCredentialView.model_validate(current)

    def list_credentials(
        self, session: Session, integration_id: UUID
    ) -> list[IngestionCredentialView]:
        integration = self._require_instrumented(session, integration_id)
        return [
            IngestionCredentialView.model_validate(row)
            for row in repo.list_for_integration(session, integration.id)
        ]

    def _require_instrumented(
        self,
        session: Session,
        integration_id: UUID,
        *,
        for_update: bool = False,
    ) -> IntegrationORM:
        integration = integration_repository.get_by_id(
            session, integration_id, for_update=for_update
        )
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        if integration.provider != IntegrationProvider.INSTRUMENTED_HTTP.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingestion credentials are only available for instrumented_http integrations",
            )
        return integration

    def _require_owned(
        self,
        session: Session,
        integration_id: UUID,
        credential_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionCredentialORM:
        row = repo.get(session, credential_id, for_update=for_update)
        if row is None or row.integration_id != integration_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingestion credential not found",
            )
        return row

    def _insert(
        self,
        session: Session,
        integration: IntegrationORM,
        *,
        label: str | None,
        rotated_from_id: UUID | None,
    ) -> _IssuedCredential:
        secret, prefix, digest = generate_credential()
        record = IngestionCredentialORM(
            id=uuid4(),
            integration_id=integration.id,
            label=label,
            key_prefix=prefix,
            secret_hash=digest,
            created_at=datetime.now(timezone.utc),
            rotated_from_id=rotated_from_id,
        )
        repo.add(session, record)
        return _IssuedCredential(record=record, secret=secret)

    def _sync_status(self, session: Session, integration: IntegrationORM) -> None:
        session.flush()
        active = repo.count_active(session, integration.id)
        desired = (
            IntegrationStatus.INSTRUMENTED.value
            if active
            else IntegrationStatus.REGISTERED.value
        )
        if integration.status != desired:
            integration.status = desired
            session.add(integration)
            session.flush()

    def _created(self, record: IngestionCredentialORM, secret: str) -> IngestionCredentialCreated:
        return IngestionCredentialCreated(
            id=record.id,
            integration_id=record.integration_id,
            label=record.label,
            key_prefix=record.key_prefix,
            credential=secret,
            created_at=record.created_at,
        )


@dataclass
class _IssuedCredential:
    record: IngestionCredentialORM
    secret: str


ingestion_credential_service = IngestionCredentialService()
