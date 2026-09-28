"""Pydantic schemas for GitHub OAuth and provider request logs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GitHubConnectionResponse(BaseModel):
    """Safe GitHub connection metadata returned to the frontend."""

    model_config = ConfigDict(from_attributes=True)

    integration_id: UUID
    connected: bool
    login: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None
    public_repos: int | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    status: str | None = None


class GitHubCheckResponse(BaseModel):
    """Result of a manual GitHub connection check."""

    ok: bool
    status: str
    login: str | None = None
    public_repos: int | None = None
    last_checked_at: datetime | None = None
    error: str | None = None


class ProviderRequestLogResponse(BaseModel):
    """Safe provider request observability row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID | None
    provider: str
    method: str
    endpoint: str
    status_code: int | None
    latency_ms: int
    timestamp: datetime
    error_message: str | None = None
    rate_limit_remaining: int | None = None
    is_simulated: bool = False
    scenario: str | None = None
