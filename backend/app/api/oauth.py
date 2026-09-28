"""GitHub OAuth callback route."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.database import get_db
from app.services.github_oauth import github_oauth_service

router = APIRouter(prefix="/api/oauth/github", tags=["oauth"])


@router.get("/callback")
def github_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """GitHub redirects here with ?code=&state= after user authorization."""
    return github_oauth_service.handle_callback(db, code=code, state=state)
