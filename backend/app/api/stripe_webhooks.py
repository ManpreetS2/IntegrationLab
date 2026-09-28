"""Stripe webhook endpoints.

Public (called by Stripe):  POST /webhooks/stripe/{integration_id}
Operator (called by the UI): /api/webhooks/stripe/*

Inbound webhooks are stored in webhook_events, not provider_request_logs
(which records outbound calls we make to providers).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.webhook import (
    ProcessDueResponse,
    WebhookEventDetail,
    WebhookEventSummary,
    WebhookProcessingStatus,
    WebhookReceiptResponse,
    WebhookSummaryResponse,
)
from app.services.stripe_webhooks import stripe_webhook_receiver
from app.services.webhook_events import webhook_event_service
from app.services.webhook_processor import stripe_webhook_processor

public_router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhooks"])
router = APIRouter(prefix="/api/webhooks/stripe", tags=["stripe-webhooks"])


@public_router.post("/{integration_id}", response_model=WebhookReceiptResponse)
async def receive_stripe_webhook(
    integration_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> WebhookReceiptResponse:
    """Verify, dedupe, and durably store a Stripe event; processing happens later."""
    # Raw bytes, never a parsed model — signature verification needs the exact body.
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    return await run_in_threadpool(
        stripe_webhook_receiver.receive,
        db,
        integration_id=integration_id,
        payload=payload,
        signature_header=signature,
    )


@router.get("/summary", response_model=WebhookSummaryResponse)
def webhook_summary(db: Session = Depends(get_db)) -> WebhookSummaryResponse:
    return webhook_event_service.summary(db)


@router.get("/events", response_model=list[WebhookEventSummary])
def list_webhook_events(
    status: WebhookProcessingStatus | None = Query(default=None),
    event_type: str | None = Query(default=None, max_length=255),
    integration_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[WebhookEventSummary]:
    """Newest-first list of received events (safe metadata only)."""
    return webhook_event_service.list_events(
        db,
        status=status.value if status else None,
        event_type=event_type,
        integration_id=integration_id,
        limit=limit,
    )


@router.get("/failed", response_model=list[WebhookEventSummary])
def list_failed_webhook_events(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[WebhookEventSummary]:
    """Failed queue — newest failure first."""
    return webhook_event_service.list_failed(db, limit=limit)


@router.post("/process-due", response_model=ProcessDueResponse)
def process_due_webhook_events(
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
) -> ProcessDueResponse:
    """Run one bounded processing tick (same code path as the CLI)."""
    return stripe_webhook_processor.process_due(db, limit=limit)


@router.get("/events/{event_id}", response_model=WebhookEventDetail)
def get_webhook_event(event_id: UUID, db: Session = Depends(get_db)) -> WebhookEventDetail:
    return webhook_event_service.detail(db, event_id)


@router.post("/events/{event_id}/process", response_model=WebhookEventDetail)
def process_webhook_event(event_id: UUID, db: Session = Depends(get_db)) -> WebhookEventDetail:
    """Process one pending/retry-scheduled event now (409 if already processing)."""
    return webhook_event_service.process_now(db, event_id)


@router.post("/events/{event_id}/retry", response_model=WebhookEventDetail)
def retry_webhook_event(event_id: UUID, db: Session = Depends(get_db)) -> WebhookEventDetail:
    """Reopen a failed (or dismissed) event with a fresh retry cycle; history kept."""
    return webhook_event_service.retry(db, event_id)


@router.post("/events/{event_id}/dismiss", response_model=WebhookEventDetail)
def dismiss_webhook_event(event_id: UUID, db: Session = Depends(get_db)) -> WebhookEventDetail:
    """Stop processing an event without deleting its history."""
    return webhook_event_service.dismiss(db, event_id)
