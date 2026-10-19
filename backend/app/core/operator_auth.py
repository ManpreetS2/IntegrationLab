"""Single-operator API authentication for portfolio deployments.

The React console stores the operator key in sessionStorage and sends it as a
Bearer token. The key is never compiled into frontend assets.

Public-by-design routes:
- /health and /ready (outside /api)
- /auth/operator (reports whether the gate is enabled)
- Stripe webhook receipt routes (outside /api)
- GitHub OAuth callback (completion still requires the start-time browser nonce)

GitHub OAuth connect is operator-gated. The console POSTs with the bearer key,
receives `{authorize_url}`, and navigates there after an HttpOnly nonce cookie
is set. Knowing an integration UUID alone cannot replace a stored connection.

POST /api/telemetry/v1/events is not operator-authenticated. It requires an
ingestion credential, checked by the route. An ingestion credential (prefix
ilk_v1_) is rejected on every other /api route.
"""

from __future__ import annotations

import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

_PUBLIC_API_GET_PATHS = {"/api/oauth/github/callback"}
_TELEMETRY_INGEST_PATH = "/api/telemetry/v1/events"
_INGESTION_CREDENTIAL_PREFIX = "ilk_v1_"


def is_telemetry_ingest(path: str, method: str) -> bool:
    """True only for the SDK ingestion route, which has its own credential."""
    return method.upper() == "POST" and path == _TELEMETRY_INGEST_PATH


def is_public_api_request(path: str, method: str) -> bool:
    """Return True only for the small /api surface that must be browser-public."""
    if method.upper() != "GET":
        return False
    return path in _PUBLIC_API_GET_PATHS


def _authorization_header(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"authorization":
            return value.decode("latin-1")
    return None


def extract_bearer_token(header_value: str | None) -> str | None:
    """Extract a strict Bearer token without logging it."""
    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def operator_authorized(expected_key: str | None, authorization: str | None) -> bool:
    """Constant-time operator-key comparison.

    A missing configured key means the gate is disabled (development/test only).
    Production Settings validation requires a sufficiently long key.
    """
    if not expected_key:
        return True
    provided = extract_bearer_token(authorization)
    return bool(provided and secrets.compare_digest(expected_key, provided))


class OperatorAuthMiddleware:
    """Protect operator /api routes with a single high-entropy bearer key."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "GET").upper()

        if method == "OPTIONS" or is_telemetry_ingest(path, method):
            await self.app(scope, receive, send)
            return

        if path.startswith("/api/"):
            token = extract_bearer_token(_authorization_header(scope))
            if token and token.startswith(_INGESTION_CREDENTIAL_PREFIX):
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Ingestion credentials cannot access operator APIs"},
                )
                await response(scope, receive, send)
                return

        if not path.startswith("/api/") or is_public_api_request(path, method):
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        if not settings.operator_api_key:
            await self.app(scope, receive, send)
            return

        authorization = _authorization_header(scope)

        if operator_authorized(settings.operator_api_key, authorization):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=401,
            content={"detail": "Operator authorization required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
