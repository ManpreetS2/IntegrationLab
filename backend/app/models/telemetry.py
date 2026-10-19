"""Pydantic contracts for universal telemetry ingestion and reads.

Field names match docs/contracts/universal-telemetry-v1.md.
Extra fields are rejected so request bodies, headers, and cookies cannot be stored.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.support import Environment
from app.services.telemetry_limits import MAX_BATCH_EVENTS, MAX_DURATION_MS, MAX_ROUTE_TEMPLATE_LENGTH

_SERVICE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
_SDK_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$")
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
_PLACEHOLDER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
_LITERAL = re.compile(r"^[A-Za-z0-9._~!$&'()*+,;=-]{1,64}$")
_UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_LONG_HEX = re.compile(r"^[0-9a-fA-F]{16,}$")
_FORBIDDEN_ROUTE_CHARS = set(" ?#\\@%")


class TelemetryKind(str, Enum):
    HTTP_OBSERVATION = "http_observation"


class TelemetryProvenance(str, Enum):
    SDK_REPORTED = "sdk_reported"


class ErrorCategory(str, Enum):
    HTTP_CLIENT_ERROR = "http_client_error"
    HTTP_SERVER_ERROR = "http_server_error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


HealthName = Literal["healthy", "degraded", "failed", "unknown", "not_configured"]
Disposition = Literal["accepted", "duplicate"]


def expected_error_category(status_code: int) -> ErrorCategory | None:
    """Return the only error category allowed for an observed HTTP status."""
    if 200 <= status_code <= 399:
        return None
    if status_code == 429:
        return ErrorCategory.RATE_LIMITED
    if 400 <= status_code <= 499:
        return ErrorCategory.HTTP_CLIENT_ERROR
    if 500 <= status_code <= 599:
        return ErrorCategory.HTTP_SERVER_ERROR
    raise ValueError("status_code must be between 200 and 599")


def validate_route_template(value: str) -> str:
    """Accept a sanitized path template and reject raw URLs or identifier segments."""
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("route_template must be an absolute path template starting with /")
    if len(value) > MAX_ROUTE_TEMPLATE_LENGTH:
        raise ValueError("route_template must be at most 200 characters")
    if any(char in _FORBIDDEN_ROUTE_CHARS for char in value) or "://" in value or "//" in value:
        raise ValueError(
            "route_template must be a path template without a query, fragment, userinfo, or encoding"
        )
    if value == "/":
        return value
    segments = value.split("/")[1:]
    if not segments or any(segment == "" for segment in segments):
        raise ValueError("route_template must not contain empty segments")
    for segment in segments:
        if segment.startswith("{") or segment.endswith("}"):
            if not (segment.startswith("{") and segment.endswith("}")):
                raise ValueError("route_template placeholders must be {name}")
            name = segment[1:-1]
            if not _PLACEHOLDER.fullmatch(name):
                raise ValueError("route_template placeholder names must be identifiers")
            continue
        if segment in {".", ".."}:
            raise ValueError("route_template must not contain dot segments")
        identifier_shaped = (
            _UUID_SEGMENT.fullmatch(segment) is not None
            or _LONG_HEX.fullmatch(segment) is not None
            or (segment.isdigit() and len(segment) > 6)
        )
        if _LITERAL.fullmatch(segment) is None or identifier_shaped:
            raise ValueError(
                "route_template segments must be static literals or {placeholders}; "
                "raw identifiers are not accepted"
            )
    return value


def _strip_label(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if _LABEL.fullmatch(normalized) is None:
        raise ValueError("label contains unsupported characters")
    return normalized


class SdkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=_SERVICE.pattern)
    version: str = Field(min_length=1, max_length=32, pattern=_SDK_VERSION.pattern)


class TelemetryEventIn(BaseModel):
    """One SDK-reported HTTP observation. Bodies and headers are not fields."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    integration_id: UUID
    occurred_at: datetime
    kind: TelemetryKind
    service: str = Field(min_length=1, max_length=63, pattern=_SERVICE.pattern)
    method: HttpMethod
    route_template: str
    status_code: int | None = Field(default=None, ge=200, le=599)
    duration_ms: int = Field(ge=0, le=MAX_DURATION_MS)
    error_category: ErrorCategory | None = None
    environment: Environment
    provenance: TelemetryProvenance
    sdk: SdkMetadata | None = None

    @field_validator("event_id")
    @classmethod
    def event_id_not_nil(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("event_id must not be the nil UUID")
        return value

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value.astimezone(timezone.utc)

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("route_template")
    @classmethod
    def check_route(cls, value: str) -> str:
        return validate_route_template(value)

    @model_validator(mode="after")
    def outcome_matches_status(self) -> TelemetryEventIn:
        if self.status_code is None:
            if self.error_category not in {ErrorCategory.TIMEOUT, ErrorCategory.TRANSPORT_ERROR}:
                raise ValueError(
                    "status_code is required unless error_category is timeout or transport_error"
                )
            return self
        expected = expected_error_category(self.status_code)
        if self.error_category != expected:
            raise ValueError("error_category does not match status_code")
        return self


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[TelemetryEventIn] = Field(min_length=1, max_length=MAX_BATCH_EVENTS)


class IngestEventResult(BaseModel):
    event_id: UUID
    disposition: Disposition


class IngestResponse(BaseModel):
    integration_id: UUID
    accepted: int
    duplicates: int
    results: list[IngestEventResult]


class TelemetryEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    integration_id: UUID
    occurred_at: datetime
    received_at: datetime
    kind: str
    service: str
    method: str
    route_template: str
    status_code: int | None
    duration_ms: int
    error_category: str | None
    environment: str
    provenance: str
    sdk_name: str | None = None
    sdk_version: str | None = None
    credential_id: UUID | None = None


class TelemetryEventPage(BaseModel):
    items: list[TelemetryEventView]
    next_cursor: str | None = None


class TelemetryFailureCategory(BaseModel):
    category: str
    count: int


class TelemetryObservationMetrics(BaseModel):
    """Aggregates of SDK-reported observations. Not an externally verified SLA."""

    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    error_rate: float | None = None
    sample_count: int = 0
    average_latency_ms: int | None = None
    p95_latency_ms: int | None = None
    latest_occurred_at: datetime | None = None
    latest_status_code: int | None = None
    latest_error_category: str | None = None
    latest_duration_ms: int | None = None
    latest_route_template: str | None = None
    latest_service: str | None = None
    failure_categories: list[TelemetryFailureCategory] = Field(default_factory=list)
    provenance: Literal["sdk_reported"] = "sdk_reported"
    independently_verified: Literal[False] = False


class InstrumentedHealthResponse(BaseModel):
    integration_id: UUID
    name: str
    provider: Literal["instrumented_http"]
    connection_status: str
    configuration: str
    health: HealthName
    summary: str
    evidence: list[str]
    recommended_action: str | None = None
    last_activity_at: datetime | None = None
    window_hours: int
    window_started_at: datetime
    generated_at: datetime
    provenance: Literal["sdk_reported"] = "sdk_reported"
    independently_verified: Literal[False] = False
    metrics: TelemetryObservationMetrics


class IngestionCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=64)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return _strip_label(value)


class IngestionCredentialRotate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=64)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return _strip_label(value)


class IngestionCredentialCreated(BaseModel):
    """Returned only from create and rotate. ``credential`` is the one-time secret."""

    id: UUID
    integration_id: UUID
    label: str | None
    key_prefix: str
    credential: str
    created_at: datetime


class IngestionCredentialView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    label: str | None
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    rotated_from_id: UUID | None
