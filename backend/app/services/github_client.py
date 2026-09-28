"""Outbound GitHub HTTP client (token exchange + authenticated REST).

Never logs tokens, Authorization headers, or raw token-exchange bodies.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.oauth import provider_request_log_repository

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_SCOPE = "read:user"
REQUEST_TIMEOUT = 15.0


@dataclass
class ProviderHttpResult:
    """Outcome of one outbound provider HTTP call."""

    ok: bool
    status_code: int | None
    latency_ms: int
    data: dict[str, Any] | None
    error_code: str | None
    rate_limit_remaining: int | None = None
    headers: dict[str, str] | None = None


def classify_github_error(status_code: int | None, *, timed_out: bool = False) -> str:
    """Map transport/HTTP outcomes to safe error labels for logs/API."""
    if timed_out:
        return "github_timeout"
    if status_code is None:
        return "github_transport_error"
    if status_code == 401:
        return "github_unauthorized"
    if status_code == 403:
        return "github_forbidden"
    if status_code == 429:
        return "github_rate_limited"
    if status_code >= 500:
        return "github_server_error"
    if status_code >= 400:
        return "github_client_error"
    return "github_error"


class GitHubClient:
    """Small GitHub OAuth + REST helper."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_authorization_url(self, *, state: str, code_challenge: str) -> str:
        """Build the GitHub authorize redirect URL (no secrets beyond client_id)."""
        params = httpx.QueryParams(
            {
                "client_id": self._settings.github_client_id or "",
                "redirect_uri": self._settings.github_oauth_redirect_uri,
                "scope": GITHUB_SCOPE,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{GITHUB_AUTHORIZE_URL}?{params}"

    def exchange_code(
        self,
        session: Session,
        *,
        code: str,
        code_verifier: str,
        integration_id: UUID | None,
    ) -> ProviderHttpResult:
        """Exchange an authorization code for an access token."""
        payload = {
            "client_id": self._settings.github_client_id,
            "client_secret": self._settings.github_client_secret,
            "code": code,
            "redirect_uri": self._settings.github_oauth_redirect_uri,
            "code_verifier": code_verifier,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        return self._request(
            session,
            method="POST",
            url=GITHUB_TOKEN_URL,
            endpoint="/login/oauth/access_token",
            integration_id=integration_id,
            json_body=payload,
            headers=headers,
        )

    def get_authenticated_user(
        self,
        session: Session,
        *,
        access_token: str,
        integration_id: UUID | None,
    ) -> ProviderHttpResult:
        """GET /user with a Bearer token."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "IntegrationLab",
        }
        return self._request(
            session,
            method="GET",
            url=f"{GITHUB_API_BASE}/user",
            endpoint="/user",
            integration_id=integration_id,
            headers=headers,
        )

    def _request(
        self,
        session: Session,
        *,
        method: str,
        url: str,
        endpoint: str,
        integration_id: UUID | None,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> ProviderHttpResult:
        started = time.perf_counter()
        status_code: int | None = None
        data: dict[str, Any] | None = None
        error_code: str | None = None
        rate_limit_remaining: int | None = None
        response_headers: dict[str, str] | None = None
        timed_out = False

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.request(method, url, headers=headers, json=json_body)
            status_code = response.status_code
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            remaining = response_headers.get("x-ratelimit-remaining")
            if remaining is not None and remaining.isdigit():
                rate_limit_remaining = int(remaining)
            try:
                parsed = response.json()
                data = parsed if isinstance(parsed, dict) else {"value": parsed}
            except ValueError:
                data = None
            if response.is_success:
                ok = True
            else:
                ok = False
                error_code = classify_github_error(status_code)
        except httpx.TimeoutException:
            timed_out = True
            ok = False
            error_code = classify_github_error(None, timed_out=True)
            logger.exception("GitHub request timed out for %s %s", method, endpoint)
        except httpx.HTTPError:
            ok = False
            error_code = classify_github_error(None)
            logger.exception("GitHub transport error for %s %s", method, endpoint)

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))

        # Observability must not undo a successful provider call.
        try:
            provider_request_log_repository.create(
                session,
                integration_id=integration_id,
                provider="github",
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                latency_ms=latency_ms,
                error_message=error_code,
                rate_limit_remaining=rate_limit_remaining,
            )
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("Failed to persist provider request log for %s %s", method, endpoint)

        return ProviderHttpResult(
            ok=ok,
            status_code=status_code,
            latency_ms=latency_ms,
            data=data,
            error_code=error_code,
            rate_limit_remaining=rate_limit_remaining,
            headers=response_headers,
        )
