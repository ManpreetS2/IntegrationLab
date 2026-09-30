"""Pydantic schemas for guided diagnostic runs and checks."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


class DiagnosticRunStatus(str, Enum):
    RUNNING = "running"
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


class DiagnosticCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    check_code: str
    title: str
    status: CheckStatus
    required: bool
    evidence: str
    recommendation: str | None
    latency_ms: int | None
    observed_at: datetime


class CheckCounts(BaseModel):
    passed: int = 0
    warning: int = 0
    failed: int = 0
    unknown: int = 0


class DiagnosticRunListItem(BaseModel):
    id: UUID
    integration_id: UUID
    provider: str
    trigger: str
    started_at: datetime
    completed_at: datetime | None
    overall_status: DiagnosticRunStatus
    summary: str | None
    check_counts: CheckCounts


class DiagnosticRunResponse(DiagnosticRunListItem):
    checks: list[DiagnosticCheckResponse] = Field(default_factory=list)
