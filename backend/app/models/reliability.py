"""Pydantic schemas for reliability health, metrics, and normalized failures."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.github import ProviderRequestLogResponse
from app.models.webhook import WebhookEventSummary


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"


class LatencyBand(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    SLOW = "slow"


class FailureSource(str, Enum):
    PROVIDER_REQUEST = "provider_request"
    WEBHOOK_PROCESSING = "webhook_processing"
    FAILURE_LAB = "failure_lab"
    DIAGNOSTIC = "diagnostic"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RequestMetrics(BaseModel):
    """Real (non-simulated) outbound request metrics inside the window."""

    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    # None when there are no requests; small samples are reported as-is with request_count.
    error_rate: float | None = None
    average_latency_ms: int | None = None
    p95_latency_ms: int | None = None
    latest_latency_ms: int | None = None
    latest_latency_band: LatencyBand | None = None
    latest_status_code: int | None = None
    latest_error_code: str | None = None
    latest_endpoint: str | None = None
    latest_request_at: datetime | None = None
    rate_limit_remaining: int | None = None


class WebhookMetrics(BaseModel):
    """Webhook receipt/processing evidence for one Stripe integration."""

    verification_configured: bool
    events_total: int = 0
    events_in_window: int = 0
    duplicate_deliveries: int = 0
    pending: int = 0
    stale_pending: int = 0
    processing: int = 0
    stale_processing: int = 0
    retry_scheduled: int = 0
    failed: int = 0
    processed: int = 0
    ignored: int = 0
    dismissed: int = 0
    failed_attempts_in_window: int = 0
    successful_attempts_in_window: int = 0
    retries_scheduled_in_window: int = 0
    last_received_at: datetime | None = None


class DiagnosticRunBrief(BaseModel):
    id: UUID
    overall_status: str
    summary: str | None
    started_at: datetime
    completed_at: datetime | None


class IntegrationHealth(BaseModel):
    integration_id: UUID
    name: str
    provider: str
    connection_status: str
    configuration: str
    health: HealthState
    summary: str
    evidence: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    last_activity_at: datetime | None = None
    last_checked_at: datetime | None = None
    request_metrics: RequestMetrics | None = None
    webhook_metrics: WebhookMetrics | None = None
    latest_diagnostic: DiagnosticRunBrief | None = None


class SystemHealth(BaseModel):
    database: HealthState
    checked_at: datetime


class HealthTotals(BaseModel):
    healthy: int = 0
    degraded: int = 0
    failed: int = 0
    unknown: int = 0
    not_configured: int = 0


class OperationalMetrics(BaseModel):
    real_provider_requests: int = 0
    real_provider_errors: int = 0
    simulated_requests: int = 0
    failure_lab_runs: int = 0
    webhook_events_received: int = 0
    duplicate_webhook_deliveries: int = 0
    webhook_processed: int = 0
    webhook_retry_scheduled: int = 0
    webhook_failed: int = 0
    webhook_pending: int = 0
    diagnostic_runs: int = 0


class FailureItem(BaseModel):
    """One normalized failure from any evidence source (safe fields only)."""

    id: str
    source: FailureSource
    integration_id: UUID | None
    integration_name: str | None
    provider: str
    occurred_at: datetime
    severity: Severity
    code: str
    summary: str
    simulated: bool = False
    # Source-specific safe context (all optional).
    method: str | None = None
    endpoint: str | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    webhook_event_id: UUID | None = None
    event_type: str | None = None
    attempt_count: int | None = None
    diagnosis_title: str | None = None
    retryable: bool | None = None
    diagnostic_run_id: UUID | None = None


class ReliabilityOverview(BaseModel):
    generated_at: datetime
    window_hours: int
    system: SystemHealth
    totals: HealthTotals
    integrations: list[IntegrationHealth]
    recent_failures: list[FailureItem]
    operational: OperationalMetrics


class IntegrationReliabilityDetail(IntegrationHealth):
    generated_at: datetime
    window_hours: int
    recent_requests: list[ProviderRequestLogResponse] = Field(default_factory=list)
    recent_webhook_events: list[WebhookEventSummary] = Field(default_factory=list)
    recent_failures: list[FailureItem] = Field(default_factory=list)


class RequestMetricsResponse(BaseModel):
    window_hours: int
    provider: str | None
    integration_id: UUID | None
    is_simulated: bool | None
    metrics: RequestMetrics
