"""GitHub OAuth orchestration: start, callback, profile, connection check."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.config import Settings, get_settings
from app.core.security import (
    TokenCipher,
    TokenCipherError,
    generate_oauth_state,
    generate_pkce_pair,
    hash_oauth_state,
)
from app.db.models.integration import IntegrationORM
from app.models.github import GitHubCheckResponse, GitHubConnectionResponse
from app.models.integration import IntegrationProvider, IntegrationStatus
from app.repositories.integrations import integration_repository
from app.repositories.oauth import (
    github_profile_repository,
    oauth_credential_repository,
    oauth_session_repository,
)
from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

OAUTH_SESSION_TTL = timedelta(minutes=10)


class GitHubOAuthService:
    """Coordinates OAuth start/callback and connection checks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = GitHubClient(self.settings)

    def require_oauth_config(self) -> None:
        if not self.settings.github_oauth_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "GitHub OAuth is not configured. Set GITHUB_CLIENT_ID, "
                    "GITHUB_CLIENT_SECRET, GITHUB_OAUTH_REDIRECT_URI, and "
                    "TOKEN_ENCRYPTION_KEY."
                ),
            )

    def _load_github_integration(self, session: Session, integration_id: UUID) -> IntegrationORM:
        integration = integration_repository.get_by_id(session, integration_id)
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        if integration.provider != IntegrationProvider.GITHUB.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Integration provider must be github",
            )
        return integration

    def start_connect(self, session: Session, integration_id: UUID) -> RedirectResponse:
        """Create OAuth session and redirect the browser to GitHub."""
        self.require_oauth_config()
        integration = self._load_github_integration(session, integration_id)

        state = generate_oauth_state()
        code_verifier, code_challenge = generate_pkce_pair()
        cipher = TokenCipher()
        expires_at = datetime.now(timezone.utc) + OAUTH_SESSION_TTL

        oauth_session_repository.create(
            session,
            integration_id=integration.id,
            provider=IntegrationProvider.GITHUB.value,
            state_hash=hash_oauth_state(state),
            code_verifier_encrypted=cipher.encrypt(code_verifier),
            expires_at=expires_at,
        )
        session.commit()

        logger.info("GitHub OAuth start for integration %s", integration.id)
        authorize_url = self.client.build_authorization_url(
            state=state,
            code_challenge=code_challenge,
        )
        return RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)

    def handle_callback(
        self,
        session: Session,
        *,
        code: str | None,
        state: str | None,
        error: str | None = None,
        error_description: str | None = None,
    ) -> RedirectResponse:
        """Validate OAuth session, exchange code, fetch /user, persist connection.

        GitHub may redirect with error=access_denied when the user cancels.
        We never surface raw error_description to the frontend.
        """
        # User cancelled / denied — redirect safely without creating credentials.
        if error:
            return self._handle_oauth_error(
                session,
                state=state,
                error=error,
                error_description=error_description,
            )

        self.require_oauth_config()
        if not code or not state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing OAuth code or state",
            )

        oauth_session = oauth_session_repository.get_by_state_hash(
            session,
            hash_oauth_state(state),
        )
        if oauth_session is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
        if oauth_session.provider != IntegrationProvider.GITHUB.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
        if oauth_session.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state already used",
            )
        now = datetime.now(timezone.utc)
        expires_at = oauth_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state expired")

        integration = self._load_github_integration(session, oauth_session.integration_id)

        try:
            cipher = TokenCipher()
            code_verifier = cipher.decrypt(oauth_session.code_verifier_encrypted)
        except TokenCipherError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Token encryption is misconfigured",
            ) from exc

        token_result = self.client.exchange_code(
            session,
            code=code,
            code_verifier=code_verifier,
            integration_id=integration.id,
        )
        if not token_result.ok or not token_result.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub authorization failed.",
            )

        access_token = token_result.data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            # GitHub may return {"error": "..."} with HTTP 200.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub authorization failed.",
            )

        token_type = token_result.data.get("token_type")
        scope_value = token_result.data.get("scope")
        # Store whatever GitHub actually granted (may be narrower than requested).
        granted_scopes = scope_value if isinstance(scope_value, str) else None

        user_result = self.client.get_authenticated_user(
            session,
            access_token=access_token,
            integration_id=integration.id,
        )
        if not user_result.ok or not user_result.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub authorization failed.",
            )

        user = user_result.data
        github_user_id = user.get("id")
        login = user.get("login")
        if not isinstance(github_user_id, int) or not isinstance(login, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub authorization failed.",
            )

        try:
            encrypted_token = cipher.encrypt(access_token)
            oauth_credential_repository.upsert(
                session,
                integration_id=integration.id,
                provider=IntegrationProvider.GITHUB.value,
                access_token_encrypted=encrypted_token,
                token_type=token_type if isinstance(token_type, str) else None,
                granted_scopes=granted_scopes,
            )
            github_profile_repository.upsert(
                session,
                integration_id=integration.id,
                github_user_id=github_user_id,
                login=login,
                avatar_url=user.get("avatar_url") if isinstance(user.get("avatar_url"), str) else None,
                html_url=user.get("html_url") if isinstance(user.get("html_url"), str) else None,
                public_repos=user.get("public_repos")
                if isinstance(user.get("public_repos"), int)
                else None,
            )
            integration_repository.update_status(
                session,
                integration,
                status=IntegrationStatus.CONNECTED.value,
                last_checked_at=now,
                commit=False,
            )
            oauth_session_repository.mark_used(session, oauth_session)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to persist GitHub OAuth connection")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save GitHub connection",
            ) from None

        logger.info("GitHub OAuth connected for integration %s", integration.id)
        query = urlencode({"oauth": "github", "status": "connected"})
        return RedirectResponse(
            url=f"{self.settings.frontend_url.rstrip('/')}/?{query}",
            status_code=status.HTTP_302_FOUND,
        )

    def _handle_oauth_error(
        self,
        session: Session,
        *,
        state: str | None,
        error: str,
        error_description: str | None,
    ) -> RedirectResponse:
        """Handle GitHub OAuth denial/cancel without exposing raw descriptions."""
        # error_description is intentionally unused in redirects/logs (may be noisy).
        _ = error_description

        if state:
            oauth_session = oauth_session_repository.get_by_state_hash(
                session,
                hash_oauth_state(state),
            )
            if (
                oauth_session is not None
                and oauth_session.used_at is None
                and oauth_session.provider == IntegrationProvider.GITHUB.value
            ):
                now = datetime.now(timezone.utc)
                expires_at = oauth_session.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at >= now:
                    oauth_session_repository.mark_used(session, oauth_session)
                    session.commit()
                    logger.info(
                        "GitHub OAuth cancelled for integration %s (error=%s)",
                        oauth_session.integration_id,
                        error,
                    )

        redirect_status = "cancelled" if error == "access_denied" else "error"
        query = urlencode({"oauth": "github", "status": redirect_status})
        return RedirectResponse(
            url=f"{self.settings.frontend_url.rstrip('/')}/?{query}",
            status_code=status.HTTP_302_FOUND,
        )

    def get_connection(
        self,
        session: Session,
        integration_id: UUID,
    ) -> GitHubConnectionResponse:
        integration = self._load_github_integration(session, integration_id)
        profile = github_profile_repository.get_by_integration_id(session, integration_id)
        credential = oauth_credential_repository.get_by_integration_id(session, integration_id)

        if profile is None or credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="GitHub connection not found",
            )

        scopes = []
        if credential.granted_scopes:
            scopes = [part.strip() for part in credential.granted_scopes.split(",") if part.strip()]

        return GitHubConnectionResponse(
            integration_id=integration.id,
            connected=integration.status == IntegrationStatus.CONNECTED.value,
            login=profile.login,
            avatar_url=profile.avatar_url,
            html_url=profile.html_url,
            public_repos=profile.public_repos,
            granted_scopes=scopes,
            connected_at=profile.connected_at,
            last_synced_at=profile.last_synced_at,
            status=integration.status,
        )

    def check_connection(self, session: Session, integration_id: UUID) -> GitHubCheckResponse:
        self.require_oauth_config()
        integration = self._load_github_integration(session, integration_id)
        credential = oauth_credential_repository.get_by_integration_id(session, integration_id)
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="GitHub credentials not found",
            )

        try:
            access_token = TokenCipher().decrypt(credential.access_token_encrypted)
        except TokenCipherError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Token encryption is misconfigured",
            ) from exc

        result = self.client.get_authenticated_user(
            session,
            access_token=access_token,
            integration_id=integration.id,
        )
        now = datetime.now(timezone.utc)

        if result.ok and result.data:
            user = result.data
            github_user_id = user.get("id")
            login = user.get("login")
            if isinstance(github_user_id, int) and isinstance(login, str):
                try:
                    github_profile_repository.upsert(
                        session,
                        integration_id=integration.id,
                        github_user_id=github_user_id,
                        login=login,
                        avatar_url=user.get("avatar_url")
                        if isinstance(user.get("avatar_url"), str)
                        else None,
                        html_url=user.get("html_url")
                        if isinstance(user.get("html_url"), str)
                        else None,
                        public_repos=user.get("public_repos")
                        if isinstance(user.get("public_repos"), int)
                        else None,
                    )
                    integration_repository.update_status(
                        session,
                        integration,
                        status=IntegrationStatus.CONNECTED.value,
                        last_checked_at=now,
                        commit=False,
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.exception("Failed to update GitHub connection check")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update connection status",
                    ) from None

                return GitHubCheckResponse(
                    ok=True,
                    status=IntegrationStatus.CONNECTED.value,
                    login=login,
                    public_repos=user.get("public_repos")
                    if isinstance(user.get("public_repos"), int)
                    else None,
                    last_checked_at=now,
                    error=None,
                )

        new_status = (
            IntegrationStatus.NEEDS_SETUP.value
            if result.status_code == 401
            else integration.status
        )
        try:
            integration_repository.update_status(
                session,
                integration,
                status=new_status,
                last_checked_at=now,
                commit=False,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to persist needs_setup after GitHub check")

        return GitHubCheckResponse(
            ok=False,
            status=new_status,
            login=None,
            public_repos=None,
            last_checked_at=now,
            error=result.error_code or "github_error",
        )


github_oauth_service = GitHubOAuthService()
