"""HTTP routes for integrations (PostgreSQL-backed)."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integration import Integration, IntegrationCreate
from app.repositories.integrations import integration_repository

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
) -> Integration:
    """Create a new integration and persist it to PostgreSQL."""
    try:
        record = integration_repository.create(db, payload)
        return Integration.model_validate(record)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to create integration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None
