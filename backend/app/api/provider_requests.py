"""Provider request log listing API."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.github import ProviderRequestLogResponse
from app.repositories.oauth import provider_request_log_repository

router = APIRouter(prefix="/api/provider-requests", tags=["provider-requests"])


@router.get("", response_model=list[ProviderRequestLogResponse])
def list_provider_requests(
    provider: str | None = Query(default=None),
    integration_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ProviderRequestLogResponse]:
    """Return recent outbound provider HTTP logs (newest first, no secrets)."""
    rows = provider_request_log_repository.list_recent(
        db,
        provider=provider,
        integration_id=integration_id,
        limit=limit,
    )
    return [ProviderRequestLogResponse.model_validate(row) for row in rows]
