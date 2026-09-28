"""Pydantic models for integrations.

These models define the shape of data the API accepts and returns.
Day 1 keeps the schema small on purpose.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class IntegrationStatus(str, Enum):
    """Lifecycle status for an integration connection."""

    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    NEEDS_SETUP = "needs_setup"


class IntegrationProvider(str, Enum):
    """Supported third-party providers for Day 1."""

    GITHUB = "github"
    STRIPE = "stripe"


class IntegrationCreate(BaseModel):
    """Request body for creating a new integration."""

    name: str = Field(..., min_length=1, max_length=100)
    provider: IntegrationProvider

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Strip surrounding whitespace; reject blank/whitespace-only names."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class Integration(BaseModel):
    """Full integration record stored and returned by the API."""

    id: UUID
    name: str
    provider: IntegrationProvider
    status: IntegrationStatus
    created_at: datetime
    last_checked_at: Optional[datetime] = None
