"""Pydantic schemas for Stripe webhook receipt, processing, and operator actions."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebhookProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    IGNORED = "ignored"
    DISMISSED = "dismissed"


class AttemptOutcome(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    IGNORED = "ignored"
    FAILED = "failed"
    ABANDONED = "abandoned"


class WebhookReceiptResponse(BaseModel):
    """Small acknowledgement returned to Stripe."""

    received: bool = True
    duplicate: bool
    event_id: str


class WebhookEffectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    effect_key: str
    effect_type: str
    provider_object_id: str | None
    summary: str | None
    applied_at: datetime


class WebhookAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_number: int
    retry_cycle: int
    cycle_attempt_number: int
    started_at: datetime
    finished_at: datetime | None
    outcome: AttemptOutcome
    error_code: str | None
    error_message: str | None
    retryable: bool | None
    scheduled_delay_seconds: int | None
    manual: bool


class WebhookEventSummary(BaseModel):
    """List/queue row — safe normalized metadata only."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    provider: str
    provider_event_id: str
    event_type: str
    provider_object_id: str | None
    livemode: bool | None
    amount: int | None
    currency: str | None
    processing_status: WebhookProcessingStatus
    delivery_count: int
    attempt_count: int
    cycle_attempt_count: int
    retry_cycle: int
    manual_retry_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    first_received_at: datetime
    last_received_at: datetime
    processed_at: datetime | None
    failed_at: datetime | None
    dismissed_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None


class WebhookEventDetail(WebhookEventSummary):
    api_version: str | None
    provider_created_at: datetime | None
    processing_started_at: datetime | None
    # Rows only exist after official signature verification succeeded.
    signature_verified: bool = True
    effects: list[WebhookEffectResponse] = Field(default_factory=list)
    attempts: list[WebhookAttemptResponse] = Field(default_factory=list)


class WebhookSummaryResponse(BaseModel):
    received: int
    duplicate_deliveries: int
    pending: int
    processing: int
    processed: int
    retry_scheduled: int
    failed: int
    ignored: int
    dismissed: int


class ProcessDueResponse(BaseModel):
    processed: int = 0
    retry_scheduled: int = 0
    failed: int = 0
    ignored: int = 0
    skipped: int = 0
