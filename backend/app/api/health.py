"""Health, readiness, and operator-auth status endpoints.

Liveness (/health): is the application process alive?
Readiness (/ready): can it reach required infrastructure (PostgreSQL)?
Operator status (/auth/operator): is the single-operator gate enabled?
"""

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import check_database_connection, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe — does not contact PostgreSQL."""
    return {"status": "ok"}


@router.get("/ready")
def readiness_check(
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Readiness probe — verifies PostgreSQL connectivity."""
    try:
        check_database_connection(db)
        return {"status": "ok", "database": "reachable"}
    except SQLAlchemyError:
        logger.exception("Readiness check failed: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unreachable"}


@router.get("/auth/operator")
def operator_auth_status() -> dict[str, bool]:
    """Public capability probe; never returns the operator key."""
    return {"required": get_settings().operator_auth_required()}


@router.get("/api/auth/check")
def operator_auth_check() -> dict[str, bool]:
    """Protected lightweight endpoint used by the console to validate a key."""
    return {"authorized": True}
