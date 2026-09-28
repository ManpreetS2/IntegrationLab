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
    """Normalized outcome of one outbound provider HTTP call (real or simulated)."""

    ok: bool
    status_code: int | None
    latency_ms: int
    data: dict[str, Any] | None
    error_code: str | None
    rate_limit_remaining: int | None = None
    headers: dict[str, str] | None = None
    malformed_body: bool = False


def classify_github_error(
    status_code: int | None,
    *,
    timed_out: bool = False,
    rate_limit_remaining: int | None = None,
    malformed_body: bool = False,
    oauth_error: bool = False,
) -> str:
    """Map transport/HTTP/application outcomes to safe error labels."""
    if timed_out:
        return "github_timeout"
    if status_code is None:
        return "github_transport_error"
    if oauth_error:
        return "github_oauth_error"
    if malformed_body:
        return "github_malformed_json"
    if status_code == 401:
        return "github_unauthorized"
    if status_code == 429:
        return "github_rate_limited"
    if status_code == 403 and rate_limit_remaining == 0:
        return "github_rate_limited"
    if status_code == 403:
        return "github_forbidden"
    if status_code == 404:
        return "github_not_found"
    if status_code >= 500:
        return "github_server_error"
    if status_code >= 400:
        return "github_client_error"
    return "github_error"


def normalize_json_response(
    *,
    status_code: int,
    raw_text: str | None,
    parsed: dict[str, Any] | list[Any] | None,
    parse_failed: bool,
    rate_limit_remaining: int | None,
    expect_json: bool,
    oauth_token_endpoint: bool = False,
) -> tuple[bool, dict[str, Any] | None, str | None, bool]:
    """Derive ok / data / error_code / malformed from HTTP + body evidence.

    HTTP 2xx is not enough: OAuth error JSON and malformed bodies are failures.
    """
    data: dict[str, Any] | None
    if isinstance(parsed, dict):
        data = parsed
    elif parsed is not None:
        data = {"value": parsed}
    else:
        data = None

    if expect_json and parse_failed:
        return (
            False,
            None,
            classify_github_error(
                status_code,
                malformed_body=True,
                rate_limit_remaining=rate_limit_remaining,
            ),
            True,
        )

    if oauth_token_endpoint and isinstance(data, dict) and isinstance(data.get("error"), str):
        # GitHub token endpoint often returns HTTP 200 with {"error": "..."}.
        return (
            False,
            data,
            classify_github_error(status_code, oauth_error=True),
            False,
        )

    if 200 <= status_code < 300:
        return True, data, None, False

    return (
        False,
        data,
        classify_github_error(status_code, rate_limit_remaining=rate_limit_remaining),
        False,
    )


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
            oauth_token_endpoint=True,
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
        oauth_token_endpoint: bool = False,
    ) -> ProviderHttpResult:
        started = time.perf_counter()
        status_code: int | None = None
        data: dict[str, Any] | None = None
        error_code: str | None = None
        rate_limit_remaining: int | None = None
        response_headers: dict[str, str] | None = None
        malformed_body = False
        timed_out = False
        ok = False

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.request(method, url, headers=headers, json=json_body)
            status_code = response.status_code
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            remaining = response_headers.get("x-ratelimit-remaining")
            if remaining is not None and remaining.isdigit():
                rate_limit_remaining = int(remaining)

            parse_failed = False
            parsed: dict[str, Any] | list[Any] | None = None
            try:
                parsed_raw = response.json()
                if isinstance(parsed_raw, (dict, list)):
                    parsed = parsed_raw
                else:
                    parsed = {"value": parsed_raw}
            except ValueError:
                parse_failed = True

            ok, data, error_code, malformed_body = normalize_json_response(
                status_code=status_code,
                raw_text=None,
                parsed=parsed,
                parse_failed=parse_failed,
                rate_limit_remaining=rate_limit_remaining,
                expect_json=True,
                oauth_token_endpoint=oauth_token_endpoint,
            )
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
                is_simulated=False,
                scenario=None,
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
            malformed_body=malformed_body,
        )
