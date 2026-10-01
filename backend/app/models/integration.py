"""Pydantic API models for integrations.

These describe HTTP request/response shapes. They are intentionally
separate from SQLAlchemy ORM models.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.support import Environment


class IntegrationStatus(str, Enum):
    """Lifecycle status for an integration connection."""

    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    NEEDS_SETUP = "needs_setup"


class IntegrationProvider(str, Enum):
    """Currently supported integration providers."""

    GITHUB = "github"
    STRIPE = "stripe"


class IntegrationCriticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntegrationSupportTier(str, Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"


class IntegrationCreate(BaseModel):
    """Request body for creating a new integration."""

    name: str = Field(..., min_length=1, max_length=100)
    provider: IntegrationProvider
    environment: Environment = Environment.LOCAL
    owner_team: Optional[str] = Field(default=None, max_length=120)
    criticality: Optional[IntegrationCriticality] = None
    support_tier: Optional[IntegrationSupportTier] = None
    runbook_url: Optional[str] = Field(default=None, max_length=500)
    escalation_contact: Optional[str] = Field(default=None, max_length=200)
    go_live_date: Optional[date] = None
    expected_traffic: Optional[str] = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Strip surrounding whitespace; reject blank/whitespace-only names."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("owner_team", "escalation_contact", "expected_traffic", "runbook_url")
    @classmethod
    def strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class IntegrationUpdate(BaseModel):
    """Patch body for operational metadata (not observed health)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    environment: Optional[Environment] = None
    owner_team: Optional[str] = Field(default=None, max_length=120)
    criticality: Optional[IntegrationCriticality] = None
    support_tier: Optional[IntegrationSupportTier] = None
    runbook_url: Optional[str] = Field(default=None, max_length=500)
    escalation_contact: Optional[str] = Field(default=None, max_length=200)
    go_live_date: Optional[date] = None
    expected_traffic: Optional[str] = Field(default=None, max_length=255)
    last_verified_at: Optional[datetime] = None

    @field_validator("name", "owner_team", "escalation_contact", "expected_traffic", "runbook_url")
    @classmethod
    def strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class Integration(BaseModel):
    """Full integration record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider: IntegrationProvider
    status: IntegrationStatus
    environment: Environment = Environment.LOCAL
    owner_team: Optional[str] = None
    criticality: Optional[IntegrationCriticality] = None
    support_tier: Optional[IntegrationSupportTier] = None
    runbook_url: Optional[str] = None
    escalation_contact: Optional[str] = None
    go_live_date: Optional[date] = None
    expected_traffic: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    created_at: datetime
    last_checked_at: Optional[datetime] = None
