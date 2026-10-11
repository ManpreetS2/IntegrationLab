"""Operator APIs for ingestion credential create, list, rotate, and revoke."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.correlation import correlation_scope, parse_correlation_id
from app.core.database import get_db
from app.models.telemetry import (
    IngestionCredentialCreate,
    IngestionCredentialCreated,
    IngestionCredentialRotate,
    IngestionCredentialView,
)
from app.services.ingestion_credentials import ingestion_credential_service

router = APIRouter(prefix="/api/integrations", tags=["ingestion-credentials"])


@router.post(
    "/{integration_id}/ingestion-credentials",
    response_model=IngestionCredentialCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_ingestion_credential(
    integration_id: UUID,
    payload: IngestionCredentialCreate | None = None,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> IngestionCredentialCreated:
    body = payload or IngestionCredentialCreate()
    try:
        with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
            return ingestion_credential_service.create(
                db,
                integration_id,
                label=body.label,
                correlation_id=correlation_id,
            )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.get(
    "/{integration_id}/ingestion-credentials",
    response_model=list[IngestionCredentialView],
)
def list_ingestion_credentials(
    integration_id: UUID,
    db: Session = Depends(get_db),
) -> list[IngestionCredentialView]:
    try:
        return ingestion_credential_service.list_credentials(db, integration_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.post(
    "/{integration_id}/ingestion-credentials/{credential_id}/rotate",
    response_model=IngestionCredentialCreated,
    status_code=status.HTTP_201_CREATED,
)
def rotate_ingestion_credential(
    integration_id: UUID,
    credential_id: UUID,
    payload: IngestionCredentialRotate | None = None,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> IngestionCredentialCreated:
    body = payload or IngestionCredentialRotate()
    try:
        with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
            return ingestion_credential_service.rotate(
                db,
                integration_id,
                credential_id,
                label=body.label,
                correlation_id=correlation_id,
            )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.post(
    "/{integration_id}/ingestion-credentials/{credential_id}/revoke",
    response_model=IngestionCredentialView,
)
def revoke_ingestion_credential(
    integration_id: UUID,
    credential_id: UUID,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> IngestionCredentialView:
    try:
        with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
            return ingestion_credential_service.revoke(
                db,
                integration_id,
                credential_id,
                correlation_id=correlation_id,
            )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None
