"""GitHub integration connect / profile / check endpoints."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.core.correlation import correlation_scope, parse_correlation_id, short_entity_id
from app.core.database import get_db
from app.models.github import GitHubCheckResponse, GitHubConnectStartResponse, GitHubConnectionResponse
from app.repositories.integrations import integration_repository
from app.services.audit import audit_service
from app.services.github_oauth import github_oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["github"])


def _audit_connect_requested(
    db: Session,
    *,
    integration_id: UUID,
    correlation_id,
) -> None:
    """Best-effort audit for an authenticated GitHub connect start."""
    integration = integration_repository.get_by_id(db, integration_id)
    # Only audit a real GitHub integration handoff. Missing/wrong-provider
    # targets must not leave a misleading "requested" success trail.
    if integration is None or integration.provider != "github":
        return
    try:
        audit_service.record(
            db,
            action="github_connect_requested",
            target_type="integration",
            target_id=integration_id,
            integration_id=integration_id,
            correlation_id=correlation_id,
            actor_type="operator",
            safe_summary=(
                f"GitHub OAuth connect requested for integration "
                f"{short_entity_id(integration_id)}"
            ),
            metadata={"provider": "github"},
            commit=True,
        )
    except Exception:  # noqa: BLE001 — never weaken the OAuth start
        logger.exception("Failed to audit GitHub connect start")
        db.rollback()


@router.post(
    "/{integration_id}/github/connect",
    response_model=GitHubConnectStartResponse,
)
def connect_github_start(
    integration_id: UUID,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> JSONResponse:
    """Start GitHub OAuth for the authenticated operator.

    Creates the OAuth session, sets a per-state HttpOnly browser-nonce cookie,
    and returns ``{authorize_url}`` for the console to navigate to. Not a
    public route — the operator bearer gate applies when configured.

    There is no GET variant: browser navigation cannot send the operator
    Bearer token, so the console must POST then navigate.
    """
    with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
        _audit_connect_requested(db, integration_id=integration_id, correlation_id=correlation_id)
        return github_oauth_service.start_connect_json(db, integration_id)


@router.get("/{integration_id}/github", response_model=GitHubConnectionResponse)
def get_github_connection(
    integration_id: UUID,
    db: Session = Depends(get_db),
) -> GitHubConnectionResponse:
    """Return safe GitHub connection metadata for the dashboard."""
    return github_oauth_service.get_connection(db, integration_id)


@router.post("/{integration_id}/github/check", response_model=GitHubCheckResponse)
def check_github_connection(
    integration_id: UUID,
    db: Session = Depends(get_db),
) -> GitHubCheckResponse:
    """Decrypt stored token, call GitHub /user, update status and logs."""
    return github_oauth_service.check_connection(db, integration_id)
