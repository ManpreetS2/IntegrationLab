"""HTTP routes for operator audit events."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.support import OperatorAuditEvent
from app.repositories.support import audit_event_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-events", tags=["audit"])


@router.get("", response_model=list[OperatorAuditEvent])
def list_audit_events(
    action: Optional[str] = None,
    integration_id: Optional[UUID] = None,
    support_case_id: Optional[UUID] = None,
    target_type: Optional[str] = None,
    outcome: Optional[str] = None,
    correlation_id: Optional[UUID] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperatorAuditEvent]:
    try:
        rows = audit_event_repository.list(
            db,
            action=action,
            integration_id=integration_id,
            support_case_id=support_case_id,
            target_type=target_type,
            outcome=outcome,
            correlation_id=correlation_id,
            since=since,
            until=until,
            limit=limit,
        )
        return [OperatorAuditEvent.from_row(row) for row in rows]
    except SQLAlchemyError:
        logger.exception("Failed to list audit events")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None
