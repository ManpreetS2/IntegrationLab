"""Application settings loaded from environment variables.

One source of truth for configuration. Secrets stay out of source code.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for IntegrationLab."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        description="SQLAlchemy database URL (postgresql+psycopg://...)",
    )
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

    @field_validator("database_url")
    @classmethod
    def require_postgres_url(cls, value: str) -> str:
        """Fail clearly if DATABASE_URL is missing or not PostgreSQL."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("DATABASE_URL must not be empty")
        if not normalized.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL "
                "(postgresql+psycopg://...). SQLite fallback is not supported."
            )
        return normalized

    def github_oauth_configured(self) -> bool:
        """True when all values required to start a GitHub OAuth flow are present."""
        return bool(
            self.github_client_id
            and self.github_client_secret
            and self.github_oauth_redirect_uri
            and self.token_encryption_key
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for the process lifetime."""
    return Settings()
