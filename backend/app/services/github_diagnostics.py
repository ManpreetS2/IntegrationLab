"""Deterministic GitHub diagnostic checks.

Observational: the only side effect is the normal provider_request_logs row
written by GitHubClient for the GET /user probe (is_simulated=false). This
module never changes integration status, profile data, or credentials, and
never returns or logs the decrypted token.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import TokenCipher, TokenCipherError
from app.db.models.integration import IntegrationORM
from app.models.diagnostics import CheckStatus
from app.models.reliability import LatencyBand
from app.repositories.oauth import oauth_credential_repository
from app.services import reliability_rules as rules
from app.services.diagnostic_checks import CheckResult
from app.services.github_client import GITHUB_SCOPE, REQUEST_TIMEOUT, GitHubClient, ProviderHttpResult

PASS, WARNING, FAIL, UNKNOWN = CheckStatus.PASS, CheckStatus.WARNING, CheckStatus.FAIL, CheckStatus.UNKNOWN

RECONNECT = "Reconnect GitHub and confirm the OAuth authorization completes successfully."
QUOTA = "Review remaining quota and wait for the provider reset window before retrying."

# Checks that need a decrypted credential + live probe, in display order.
_PROBE_CHECKS = [
    ("github_api_reachability", "GitHub API reachability", True),
    ("github_authentication", "GitHub authentication", True),
    ("github_identity", "Authenticated identity", False),
    ("github_scopes", "Granted scopes", False),
    ("github_rate_limit", "Rate limit", False),
    ("github_latency", "Request latency", False),
]


def _parse_scopes(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.replace(" ", ",").split(",") if part.strip()}


def _skipped(reason: str) -> list[CheckResult]:
    return [
        CheckResult(code, title, UNKNOWN, f"Skipped: {reason}", required=required)
        for code, title, required in _PROBE_CHECKS
    ]


def _reset_time(headers: dict[str, str] | None) -> str | None:
    raw = (headers or {}).get("x-ratelimit-reset")
    if raw and raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%H:%M UTC")
    return None


def run_github_checks(
    session: Session,
    integration: IntegrationORM,
    *,
    settings: Settings,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    # 1. Configuration presence (never values).
    required_config = {
        "GITHUB_CLIENT_ID": settings.github_client_id,
        "GITHUB_CLIENT_SECRET": settings.github_client_secret,
        "GITHUB_OAUTH_REDIRECT_URI": settings.github_oauth_redirect_uri,
        "TOKEN_ENCRYPTION_KEY": settings.token_encryption_key,
    }
    missing = [name for name, value in required_config.items() if not value]
    checks.append(
        CheckResult(
            "github_oauth_configuration",
            "OAuth configuration",
            FAIL if missing else PASS,
            f"Missing configuration: {', '.join(missing)} (values are never displayed)."
            if missing
            else "GitHub client ID, client secret, redirect URI, and token encryption key are configured.",
            "Set the missing variables in backend/.env and restart the API." if missing else None,
            required=True,
        )
    )

    # 2. Connection state (informational — diagnostics never rewrite it).
    state_status = {"connected": PASS, "needs_setup": WARNING}.get(integration.status, WARNING)
    checks.append(
        CheckResult(
            "github_connection_state",
            "Connection state",
            state_status,
            f"Integration status is {integration.status}.",
            None if state_status == PASS else RECONNECT,
        )
    )

    # 3. Stored credential.
    credential = oauth_credential_repository.get_by_integration_id(session, integration.id)
    if credential is None:
        checks.append(
            CheckResult(
                "github_credential",
                "Stored credential",
                FAIL,
                "No encrypted OAuth credential is stored for this integration.",
                "Connect GitHub to authorize IntegrationLab with the read:user scope.",
                required=True,
            )
        )
        checks.append(
            CheckResult(
                "github_token_decryption",
                "Credential decryption",
                UNKNOWN,
                "Skipped: no stored credential.",
                required=True,
            )
        )
        return checks + _skipped("no stored credential.")
    checks.append(
        CheckResult(
            "github_credential",
            "Stored credential",
            PASS,
            "An encrypted OAuth credential is stored (value not displayed).",
            required=True,
        )
    )

    # 4. Decryption.
    try:
        access_token = TokenCipher(settings.token_encryption_key or "").decrypt(
            credential.access_token_encrypted
        )
    except TokenCipherError:
        checks.append(
            CheckResult(
                "github_token_decryption",
                "Credential decryption",
                FAIL,
                "Stored credential could not be decrypted (token_encryption_error): the encryption "
                "key is missing, has changed, or the ciphertext is invalid.",
                "Restore the original TOKEN_ENCRYPTION_KEY, or reconnect GitHub to store a credential "
                "encrypted with the current key.",
                required=True,
            )
        )
        return checks + _skipped("credential could not be decrypted.")
    checks.append(
        CheckResult(
            "github_token_decryption",
            "Credential decryption",
            PASS,
            "Stored credential decrypted successfully with the configured key.",
            required=True,
        )
    )

    # 5. Live probe: real GET /user (logged as a normal, non-simulated request).
    result = GitHubClient(settings).get_authenticated_user(
        session, access_token=access_token, integration_id=integration.id
    )
    del access_token
    checks.extend(_probe_checks(result, credential.granted_scopes))
    return checks


def _probe_checks(result: ProviderHttpResult, stored_scopes: str | None) -> list[CheckResult]:
    code = result.status_code
    ms = result.latency_ms
    checks: list[CheckResult] = []

    # Reachability
    if code is None:
        evidence = (
            f"GET /user timed out (client timeout {REQUEST_TIMEOUT:.0f}s)."
            if result.error_code == "github_timeout"
            else f"GET /user failed before an HTTP response ({result.error_code})."
        )
        checks.append(
            CheckResult(
                "github_api_reachability",
                "GitHub API reachability",
                FAIL,
                evidence,
                "Check network/DNS connectivity to api.github.com, then re-run diagnostics.",
                required=True,
                latency_ms=ms,
            )
        )
    elif code >= 500:
        checks.append(
            CheckResult(
                "github_api_reachability",
                "GitHub API reachability",
                WARNING,
                f"GitHub responded with HTTP {code} in {ms}ms.",
                "Check githubstatus.com and re-run diagnostics later; this does not indicate a "
                "credential problem.",
                required=True,
                latency_ms=ms,
            )
        )
    else:
        checks.append(
            CheckResult(
                "github_api_reachability",
                "GitHub API reachability",
                PASS,
                f"GitHub responded with HTTP {code} in {ms}ms.",
                required=True,
                latency_ms=ms,
            )
        )

    # Authentication
    rate_limited = result.error_code == "github_rate_limited"
    if result.ok:
        auth = CheckResult("github_authentication", "GitHub authentication", PASS, f"GET /user returned HTTP {code}.")
    elif code == 401:
        auth = CheckResult("github_authentication", "GitHub authentication", FAIL, "GET /user returned HTTP 401.", RECONNECT)
    elif code == 403 and not rate_limited:
        auth = CheckResult(
            "github_authentication",
            "GitHub authentication",
            FAIL,
            "GET /user returned HTTP 403 (github_forbidden).",
            "Confirm the OAuth app authorization has not been revoked or restricted, then reconnect GitHub.",
        )
    elif rate_limited:
        auth = CheckResult(
            "github_authentication",
            "GitHub authentication",
            UNKNOWN,
            f"Authentication could not be confirmed: GitHub rate limit reached (HTTP {code}).",
            QUOTA,
        )
    else:
        reason = f"HTTP {code}" if code is not None else "no HTTP response"
        detail = f" ({result.error_code})" if result.error_code else ""
        auth = CheckResult(
            "github_authentication",
            "GitHub authentication",
            UNKNOWN,
            f"Authentication could not be confirmed: {reason}{detail}.",
            "Re-run diagnostics once GitHub responds normally.",
        )
    auth.required = True
    auth.latency_ms = ms
    checks.append(auth)

    # Identity
    if result.ok and result.data is not None:
        user_id, login = result.data.get("id"), result.data.get("login")
        if isinstance(user_id, int) and isinstance(login, str):
            checks.append(
                CheckResult(
                    "github_identity",
                    "Authenticated identity",
                    PASS,
                    f"GET /user identified login '{login}' (id {user_id}).",
                )
            )
        else:
            checks.append(
                CheckResult(
                    "github_identity",
                    "Authenticated identity",
                    FAIL,
                    "GET /user succeeded but the response is missing the required id/login fields.",
                    "Re-run diagnostics; if it persists, reconnect GitHub.",
                )
            )
    else:
        checks.append(
            CheckResult(
                "github_identity", "Authenticated identity", UNKNOWN, "Skipped: authentication was not confirmed."
            )
        )

    # Scopes — stored grant first, live X-OAuth-Scopes header as supporting evidence.
    stored = _parse_scopes(stored_scopes)
    live = _parse_scopes((result.headers or {}).get("x-oauth-scopes"))
    if GITHUB_SCOPE in stored or "user" in stored:
        scope = CheckResult(
            "github_scopes", "Granted scopes", PASS, f"Stored granted scopes include {GITHUB_SCOPE}."
        )
    elif GITHUB_SCOPE in live or "user" in live:
        scope = CheckResult(
            "github_scopes",
            "Granted scopes",
            PASS,
            f"Stored scope metadata lacks {GITHUB_SCOPE}, but the live X-OAuth-Scopes header includes it.",
        )
    elif result.ok:
        scope = CheckResult(
            "github_scopes",
            "Granted scopes",
            WARNING,
            f"Granted scope metadata does not include {GITHUB_SCOPE}; current /user request still succeeded.",
            f"Reconnect GitHub if a feature requires {GITHUB_SCOPE}; the current connection still authenticates.",
        )
    else:
        scope = CheckResult(
            "github_scopes",
            "Granted scopes",
            WARNING,
            f"Granted scope metadata does not include {GITHUB_SCOPE}.",
            RECONNECT,
        )
    checks.append(scope)

    # Rate limit
    remaining = result.rate_limit_remaining
    reset = _reset_time(result.headers)
    reset_text = f" Resets at {reset}." if reset else ""
    if remaining is None:
        checks.append(
            CheckResult("github_rate_limit", "Rate limit", UNKNOWN, "No X-RateLimit-Remaining header was observed.")
        )
    elif remaining < rules.RATE_LIMIT_LOW_REMAINING:
        checks.append(
            CheckResult(
                "github_rate_limit",
                "Rate limit",
                WARNING,
                f"X-RateLimit-Remaining is {remaining} (local low threshold {rules.RATE_LIMIT_LOW_REMAINING}).{reset_text}",
                QUOTA,
            )
        )
    else:
        checks.append(
            CheckResult("github_rate_limit", "Rate limit", PASS, f"X-RateLimit-Remaining is {remaining}.{reset_text}")
        )

    # Latency (project thresholds, not GitHub guarantees)
    band = rules.latency_band(ms) if code is not None else None
    if band is None:
        checks.append(
            CheckResult("github_latency", "Request latency", UNKNOWN, "No HTTP response, so latency is not meaningful.")
        )
    elif band == LatencyBand.SLOW:
        checks.append(
            CheckResult(
                "github_latency",
                "Request latency",
                WARNING,
                f"GET /user took {ms}ms (local slow threshold {rules.LATENCY_SLOW_MS}ms).",
                "Re-run diagnostics; if latency stays high, check the network path to api.github.com.",
                latency_ms=ms,
            )
        )
    else:
        note = (
            f" (elevated; local threshold {rules.LATENCY_ELEVATED_MS}ms)" if band == LatencyBand.ELEVATED else ""
        )
        checks.append(
            CheckResult("github_latency", "Request latency", PASS, f"GET /user took {ms}ms{note}.", latency_ms=ms)
        )
    return checks
