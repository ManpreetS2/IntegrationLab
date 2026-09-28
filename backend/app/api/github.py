"""GitHub integration connect / profile / check endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.database import get_db
from app.models.github import GitHubCheckResponse, GitHubConnectionResponse
from app.services.github_oauth import github_oauth_service

router = APIRouter(prefix="/api/integrations", tags=["github"])


@router.get("/{integration_id}/github/connect")
def connect_github(
    integration_id: UUID,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Start GitHub OAuth (browser navigation; returns a redirect)."""
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
