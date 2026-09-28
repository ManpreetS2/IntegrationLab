"""Pydantic schemas for Failure Lab."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FailureScenario(str, Enum):
    """Server-defined Failure Lab scenarios (no arbitrary URLs/methods)."""

    UNAUTHORIZED_401 = "unauthorized_401"
    FORBIDDEN_403 = "forbidden_403"
    NOT_FOUND_404 = "not_found_404"
    RATE_LIMITED_429 = "rate_limited_429"
    PROVIDER_500 = "provider_500"
    TIMEOUT = "timeout"
    MALFORMED_JSON = "malformed_json"
    TRANSPORT_ERROR = "transport_error"


class FailureScenarioInfo(BaseModel):
    id: FailureScenario
    label: str
    description: str


class FailureLabRunRequest(BaseModel):
    integration_id: UUID
    scenario: FailureScenario


class ObservedResult(BaseModel):
    status_code: int | None
    latency_ms: int
    error_code: str | None = None
    rate_limit_remaining: int | None = None


class DiagnosisResult(BaseModel):
    code: str
    title: str
    summary: str
    retryable: bool
    evidence: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)


class RequestInfo(BaseModel):
    method: str
    endpoint: str


class FailureLabRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    provider: str
    scenario: FailureScenario
    request: RequestInfo
    observed: ObservedResult
    diagnosis: DiagnosisResult
    created_at: datetime


class FailureLabRunListItem(BaseModel):
    """Compact history row for the Failure Lab table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    provider: str
    scenario: FailureScenario
    status_code: int | None
    latency_ms: int
    error_code: str | None
    diagnosis_code: str
    diagnosis_title: str
    retryable: bool
    created_at: datetime
