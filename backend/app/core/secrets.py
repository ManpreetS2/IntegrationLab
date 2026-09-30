"""Safe helpers for constructing configuration from Secrets Manager JSON.

These helpers never log secret values. Callers must not print the returned
database URL or app-secret payload.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class SecretConfigError(ValueError):
    """Raised when a required secret payload cannot be used safely."""


def parse_secret_json(raw: str | None, *, label: str) -> dict[str, Any] | None:
    """Parse a Secrets Manager JSON string.

    Returns None when raw is empty/unset. Raises SecretConfigError on malformed
    JSON so callers can fail the features that need the secret without dumping
    the payload into logs.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Malformed %s JSON; refusing to parse secret payload", label)
        raise SecretConfigError(f"Malformed {label} JSON") from exc
    if not isinstance(parsed, dict):
        logger.error("%s must be a JSON object", label)
        raise SecretConfigError(f"{label} must be a JSON object")
    return parsed


def build_database_url(
    *,
    database_url: str | None,
    db_host: str | None,
    db_port: int | None,
    db_name: str | None,
    db_user: str | None,
    db_secret_json: str | None,
) -> str:
    """Resolve the SQLAlchemy PostgreSQL URL.

    Precedence:
    1. Explicit DATABASE_URL (local/dev and CI)
    2. DB_HOST/DB_PORT/DB_NAME + INTEGRATIONLAB_DB_SECRET JSON
       (username/password; username falls back to DB_USER)
    """
    if database_url and database_url.strip():
        return database_url.strip()

    missing = [
        name
        for name, value in (
            ("DB_HOST", db_host),
            ("DB_PORT", db_port),
            ("DB_NAME", db_name),
            ("INTEGRATIONLAB_DB_SECRET", db_secret_json),
        )
        if value is None or (isinstance(value, str) and not value.strip())
    ]
    if missing:
        raise SecretConfigError(
            "DATABASE_URL is unset and AWS database inputs are incomplete "
            f"(missing: {', '.join(missing)})"
        )

    secret = parse_secret_json(db_secret_json, label="INTEGRATIONLAB_DB_SECRET")
    assert secret is not None  # guarded by missing check above

    username = str(secret.get("username") or db_user or "").strip()
    password = str(secret.get("password") or "")
    if not username or not password:
        raise SecretConfigError(
            "INTEGRATIONLAB_DB_SECRET must include non-empty username and password"
        )

    user_enc = quote_plus(username)
    pass_enc = quote_plus(password)
    host = str(db_host).strip()
    port = int(db_port)  # type: ignore[arg-type]
    name = str(db_name).strip()
    return f"postgresql+psycopg://{user_enc}:{pass_enc}@{host}:{port}/{name}"


def merge_app_secrets(
    *,
    app_secrets_json: str | None,
    github_client_id: str | None,
    github_client_secret: str | None,
    token_encryption_key: str | None,
    stripe_webhook_secret: str | None,
) -> dict[str, str | None]:
    """Merge INTEGRATIONLAB_APP_SECRETS with explicit environment overrides.

    Explicit environment variables always win when set. Malformed JSON leaves
    optional provider features unset (they already degrade to not_configured)
    rather than crashing the whole process — unless production startup later
    decides otherwise for database configuration.
    """
    merged: dict[str, str | None] = {
        "github_client_id": github_client_id,
        "github_client_secret": github_client_secret,
        "token_encryption_key": token_encryption_key,
        "stripe_webhook_secret": stripe_webhook_secret,
    }

    try:
        secret = parse_secret_json(app_secrets_json, label="INTEGRATIONLAB_APP_SECRETS")
    except SecretConfigError:
        # Optional providers can remain not_configured; never echo the payload.
        return merged

    if not secret:
        return merged

    key_map = {
        "GITHUB_CLIENT_ID": "github_client_id",
        "GITHUB_CLIENT_SECRET": "github_client_secret",
        "TOKEN_ENCRYPTION_KEY": "token_encryption_key",
        "STRIPE_WEBHOOK_SECRET": "stripe_webhook_secret",
    }
    for secret_key, field_name in key_map.items():
        if merged[field_name]:
            continue
        value = secret.get(secret_key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            merged[field_name] = text
    return merged
