"""Pydantic API models for support cases, notes, evidence, timeline, and audit."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Environment(str, Enum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class CaseSeverity(str, Enum):
    """Portfolio severity labels (not company-wide SLAs)."""

    SEV1 = "SEV1"  # critical capability unavailable / major business impact
    SEV2 = "SEV2"  # serious degradation or important workflow failing
    SEV3 = "SEV3"  # limited impact / partial failure
    SEV4 = "SEV4"  # low-impact support/configuration investigation


class CaseStatus(str, Enum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class EvidenceType(str, Enum):
    PROVIDER_REQUEST = "provider_request"
    WEBHOOK_EVENT = "webhook_event"
    WEBHOOK_ATTEMPT = "webhook_attempt"
    DIAGNOSTIC_RUN = "diagnostic_run"
    FAILURE_LAB_RUN = "failure_lab_run"
    AUDIT_EVENT = "audit_event"


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


def _strip_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class SupportCaseCreate(BaseModel):
    integration_id: UUID
    title: str = Field(..., min_length=1, max_length=200)
    severity: CaseSeverity = CaseSeverity.SEV3
    owner: Optional[str] = Field(default=None, max_length=120)
    impact_summary: Optional[str] = Field(default=None, max_length=4000)
    suspected_cause: Optional[str] = Field(default=None, max_length=4000)
    environment: Optional[Environment] = None
    source_evidence_type: Optional[EvidenceType] = None
    source_evidence_id: Optional[UUID] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("owner", "impact_summary", "suspected_cause")
    @classmethod
    def normalize_optional(cls, value: Optional[str]) -> Optional[str]:
        return _strip_optional(value)

    @model_validator(mode="after")
    def source_evidence_pair(self) -> "SupportCaseCreate":
        has_type = self.source_evidence_type is not None
        has_id = self.source_evidence_id is not None
        if has_type != has_id:
            raise ValueError(
                "source_evidence_type and source_evidence_id must both be provided or both omitted"
            )
        return self


class SupportCaseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    severity: Optional[CaseSeverity] = None
    status: Optional[CaseStatus] = None
    owner: Optional[str] = Field(default=None, max_length=120)
    impact_summary: Optional[str] = Field(default=None, max_length=4000)
    suspected_cause: Optional[str] = Field(default=None, max_length=4000)
    confirmed_root_cause: Optional[str] = Field(default=None, max_length=4000)
    mitigation_summary: Optional[str] = Field(default=None, max_length=4000)
    resolution_summary: Optional[str] = Field(default=None, max_length=4000)

    @field_validator(
        "title",
        "owner",
        "impact_summary",
        "suspected_cause",
        "confirmed_root_cause",
        "mitigation_summary",
        "resolution_summary",
    )
    @classmethod
    def normalize_optional(cls, value: Optional[str]) -> Optional[str]:
        return _strip_optional(value)


class SupportCaseNoteCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        return _strip_required(value)


class SupportCaseEvidenceCreate(BaseModel):
    evidence_type: EvidenceType
    evidence_id: UUID
    safe_label: Optional[str] = Field(default=None, max_length=255)

    @field_validator("safe_label")
    @classmethod
    def normalize_label(cls, value: Optional[str]) -> Optional[str]:
        return _strip_optional(value)


class SupportCaseNote(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    support_case_id: UUID
    body: str
    correlation_id: Optional[UUID] = None
    created_at: datetime


class SupportCaseEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    support_case_id: UUID
    evidence_type: EvidenceType
    evidence_id: UUID
    safe_label: str
    is_simulated: bool
    correlation_id: Optional[UUID] = None
    pinned_at: datetime


class SupportCase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_number: str
    integration_id: UUID
    environment: Environment
    title: str
    severity: CaseSeverity
    status: CaseStatus
    owner: Optional[str] = None
    impact_summary: Optional[str] = None
    suspected_cause: Optional[str] = None
    confirmed_root_cause: Optional[str] = None
    mitigation_summary: Optional[str] = None
    resolution_summary: Optional[str] = None
    correlation_id: Optional[UUID] = None
    opened_at: datetime
    acknowledged_at: Optional[datetime] = None
    identified_at: Optional[datetime] = None
    monitoring_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    reopened_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SupportCaseDetail(SupportCase):
    notes: list[SupportCaseNote] = Field(default_factory=list)
    evidence: list[SupportCaseEvidence] = Field(default_factory=list)


class TimelineItem(BaseModel):
    """Unified case timeline item.

    ``timestamp`` is the sort key. For linked evidence it is ``occurred_at``
    (when the underlying evidence happened). Operator pin actions appear
    separately via case history at ``pinned_at``.
    """

    timestamp: datetime
    type: str
    title: str
    summary: str
    source_type: Optional[str] = None
    source_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None
    correlation_short: Optional[str] = None
    is_simulated: bool = False
    occurred_at: Optional[datetime] = None
    pinned_at: Optional[datetime] = None


class OperatorAuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    target_type: str
    target_id: Optional[str] = None
    integration_id: Optional[UUID] = None
    support_case_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None
    actor_type: str
    outcome: str
    safe_summary: str
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> "OperatorAuditEvent":
        return cls(
            id=row.id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            integration_id=row.integration_id,
            support_case_id=row.support_case_id,
            correlation_id=row.correlation_id,
            actor_type=row.actor_type,
            outcome=row.outcome,
            safe_summary=row.safe_summary,
            metadata=row.metadata_json,
            created_at=row.created_at,
        )
