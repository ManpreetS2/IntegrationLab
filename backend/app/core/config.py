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

    # Env vars: DATABASE_URL, TEST_DATABASE_URL
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


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for the process lifetime."""
    return Settings()
