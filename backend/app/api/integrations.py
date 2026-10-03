"""HTTP routes for integrations (PostgreSQL-backed)."""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.correlation import correlation_scope, parse_correlation_id, short_entity_id
from app.core.database import get_db
from app.models.integration import Integration, IntegrationCreate, IntegrationUpdate
from app.repositories.integrations import integration_repository
from app.services.audit import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("", response_model=List[Integration])
def list_integrations(db: Session = Depends(get_db)) -> List[Integration]:
    """Return all integrations from PostgreSQL."""
    try:
        records = integration_repository.list_all(db)
        return [Integration.model_validate(record) for record in records]
    except SQLAlchemyError:
        logger.exception("Failed to list integrations")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.post("", response_model=Integration, status_code=status.HTTP_201_CREATED)
def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> Integration:
    """Create a new integration and persist it to PostgreSQL."""
    try:
        with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
            # One transaction: integration row + audit event.
            record = integration_repository.create(db, payload, commit=False)
            audit_service.record(
                db,
                action="integration_created",
                target_type="integration",
                target_id=record.id,
                integration_id=record.id,
                correlation_id=correlation_id,
                safe_summary=(
                    f"Created {record.provider} integration {short_entity_id(record.id)}"
                ),
                metadata={
                    "provider": record.provider,
                    "environment": record.environment,
                },
                commit=False,
            )
            db.commit()
            db.refresh(record)
        return Integration.model_validate(record)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to create integration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.patch("/{integration_id}", response_model=Integration)
def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdate,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> Integration:
    """Update operational metadata for an integration."""
    try:
        record = integration_repository.get_by_id(db, integration_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
            updated = integration_repository.update_metadata(db, record, payload, commit=False)
            audit_service.record(
                db,
                action="integration_updated",
                target_type="integration",
                target_id=updated.id,
                integration_id=updated.id,
                correlation_id=correlation_id,
                safe_summary=(
                    f"Updated {updated.provider} integration {short_entity_id(updated.id)} metadata"
                ),
                metadata={
                    "provider": updated.provider,
                    "environment": updated.environment,
                },
                commit=False,
            )
            db.commit()
            db.refresh(updated)
        return Integration.model_validate(updated)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to update integration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None
