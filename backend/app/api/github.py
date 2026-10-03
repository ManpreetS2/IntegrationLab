"""GitHub integration connect / profile / check endpoints."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.correlation import correlation_scope, parse_correlation_id, short_entity_id
from app.core.database import get_db
from app.models.github import GitHubCheckResponse, GitHubConnectionResponse
from app.services.audit import audit_service
from app.services.github_oauth import github_oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["github"])


@router.get("/{integration_id}/github/connect")
def connect_github(
    integration_id: UUID,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> RedirectResponse:
    """Start GitHub OAuth (browser navigation; returns a redirect).

    Intentionally public for browser handoff. Audit uses actor_type
    ``browser_handoff`` — not authenticated per-user identity. Audit failure
    must not block the OAuth redirect.
    """
    with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
        try:
            audit_service.record(
                db,
                action="github_connect_started",
                target_type="integration",
                target_id=integration_id,
                integration_id=integration_id,
                correlation_id=correlation_id,
                actor_type="browser_handoff",
                safe_summary=(
                    f"GitHub OAuth connect started for integration "
                    f"{short_entity_id(integration_id)}"
                ),
                metadata={"provider": "github"},
                commit=True,
            )
        except Exception:  # noqa: BLE001 — never weaken the public OAuth handoff
            logger.exception("Failed to audit GitHub connect handoff")
            db.rollback()
        return github_oauth_service.start_connect(db, integration_id)


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
