"""Application settings loaded from environment variables.

One source of truth for configuration. Secrets stay out of source code.

Local development uses DATABASE_URL. AWS deployment may instead inject
DB_HOST/DB_PORT/DB_NAME plus INTEGRATIONLAB_DB_SECRET (JSON) and
INTEGRATIONLAB_APP_SECRETS (JSON). Explicit environment variables always win
over secret JSON values.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets import SecretConfigError, build_database_url, merge_app_secrets

logger = logging.getLogger(__name__)

AppEnv = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Typed settings for IntegrationLab."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = "development"
    app_version: str | None = Field(
        default=None,
        description="Optional deploy identifier (usually a Git SHA).",
    )

    # Prefer DATABASE_URL. When unset, AWS pieces below construct one.
    database_url: str | None = None
    db_host: str | None = None
    db_port: int | None = 5432
    db_name: str | None = None
    db_user: str | None = None
    integrationlab_db_secret: str | None = None
    integrationlab_app_secrets: str | None = None

    test_database_url: str | None = Field(
        default=None,
        description="Optional dedicated URL for pytest (must look like a test DB).",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # Optional GitHub OAuth settings — app boots without them; OAuth routes fail clearly.
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str = "http://localhost:8000/api/oauth/github/callback"
    frontend_url: str = "http://localhost:5173"
    token_encryption_key: str | None = None

    # Optional Stripe webhook signing secret — app boots without it; the webhook
    # endpoint returns 503 until it is configured.
    stripe_webhook_secret: str | None = None

    @model_validator(mode="after")
    def resolve_secrets_and_database(self) -> Settings:
        """Fill optional secrets from JSON, then resolve DATABASE_URL."""
        merged = merge_app_secrets(
            app_secrets_json=self.integrationlab_app_secrets,
            github_client_id=self.github_client_id,
            github_client_secret=self.github_client_secret,
            token_encryption_key=self.token_encryption_key,
            stripe_webhook_secret=self.stripe_webhook_secret,
        )
        object.__setattr__(self, "github_client_id", merged["github_client_id"])
        object.__setattr__(self, "github_client_secret", merged["github_client_secret"])
        object.__setattr__(self, "token_encryption_key", merged["token_encryption_key"])
        object.__setattr__(self, "stripe_webhook_secret", merged["stripe_webhook_secret"])

        try:
            resolved = build_database_url(
                database_url=self.database_url,
                db_host=self.db_host,
                db_port=self.db_port,
                db_name=self.db_name,
                db_user=self.db_user,
                db_secret_json=self.integrationlab_db_secret,
            )
        except SecretConfigError as exc:
            if self.app_env == "production":
                raise ValueError(
                    "Production requires DATABASE_URL or complete AWS database "
                    "configuration (DB_HOST, DB_PORT, DB_NAME, INTEGRATIONLAB_DB_SECRET)."
                ) from exc
            raise ValueError(str(exc)) from exc

        if not resolved.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL "
                "(postgresql+psycopg://...). SQLite fallback is not supported."
            )
        object.__setattr__(self, "database_url", resolved)
        return self

    def require_database_url(self) -> str:
        """Return the resolved PostgreSQL URL (always set after validation)."""
        if not self.database_url:
            raise RuntimeError("DATABASE_URL was not resolved")
        return self.database_url

    def github_oauth_configured(self) -> bool:
        """True when all values required to start a GitHub OAuth flow are present."""
        return bool(
            self.github_client_id
            and self.github_client_secret
            and self.github_oauth_redirect_uri
            and self.token_encryption_key
        )

    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for the process lifetime."""
    settings = Settings()
    # Never log connection strings or secret payloads.
    logger.info(
        "IntegrationLab starting (env=%s version=%s)",
        settings.app_env,
        settings.app_version or "unknown",
    )
    return settings
