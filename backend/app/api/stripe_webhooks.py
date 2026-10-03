"""Stripe webhook endpoints.

Public (called by Stripe):  POST /webhooks/stripe/{integration_id}
Operator (called by the UI): /api/webhooks/stripe/*

Inbound webhooks are stored in webhook_events, not provider_request_logs
(which records outbound calls we make to providers).
"""

from collections.abc import Callable
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.correlation import correlation_scope, parse_correlation_id, short_entity_id
from app.core.database import SessionLocal, get_db
from app.models.webhook import (
    ProcessDueResponse,
    WebhookEventDetail,
    WebhookEventSummary,
    WebhookProcessingStatus,
    WebhookReceiptResponse,
    WebhookSummaryResponse,
)
from app.services.audit import audit_service
from app.services.stripe_webhooks import stripe_webhook_receiver
from app.services.webhook_events import webhook_event_service
from app.services.webhook_processor import stripe_webhook_processor

public_router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhooks"])
router = APIRouter(prefix="/api/webhooks/stripe", tags=["stripe-webhooks"])


# Sessions for the public webhook route are created inside the worker thread,
# never passed across the async/threadpool boundary.
webhook_session_factory: Callable[[], Session] = SessionLocal


def _receive_with_own_session(
    integration_id: UUID,
    payload: bytes,
    signature_header: str | None,
) -> WebhookReceiptResponse:
    session = webhook_session_factory()
    try:
        return stripe_webhook_receiver.receive(
            session,
            integration_id=integration_id,
            payload=payload,
            signature_header=signature_header,
        )
    finally:
        session.close()


@public_router.post("/{integration_id}", response_model=WebhookReceiptResponse)
async def receive_stripe_webhook(integration_id: UUID, request: Request) -> WebhookReceiptResponse:
    """Verify, dedupe, and durably store a Stripe event; processing happens later."""
    # Raw bytes, never a parsed model — signature verification needs the exact body.
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    return await run_in_threadpool(_receive_with_own_session, integration_id, payload, signature)


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
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> ProcessDueResponse:
    """Run one bounded processing tick (same code path as the CLI)."""
    with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
        result = stripe_webhook_processor.process_due(db, limit=limit)
        audit_service.record(
            db,
            action="webhook_process_due_requested",
            target_type="webhook_batch",
            target_id=None,
            correlation_id=correlation_id,
            safe_summary=f"Processed due Stripe webhooks (limit={limit})",
            metadata={
                "limit": limit,
                "processed": result.processed,
                "retry_scheduled": result.retry_scheduled,
                "failed": result.failed,
                "ignored": result.ignored,
                "skipped": result.skipped,
            },
            commit=True,
        )
        return result


@router.get("/events/{event_id}", response_model=WebhookEventDetail)
def get_webhook_event(event_id: UUID, db: Session = Depends(get_db)) -> WebhookEventDetail:
    return webhook_event_service.detail(db, event_id)


@router.post("/events/{event_id}/process", response_model=WebhookEventDetail)
def process_webhook_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> WebhookEventDetail:
    """Process one pending/retry-scheduled event now (409 if already processing)."""
    with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
        detail = webhook_event_service.process_now(db, event_id)
        audit_service.record(
            db,
            action="webhook_process_requested",
            target_type="webhook_event",
            target_id=event_id,
            integration_id=detail.integration_id,
            correlation_id=correlation_id,
            safe_summary=(
                f"Processed Stripe webhook event {short_entity_id(event_id)} "
                f"→ {detail.processing_status}"
            ),
            metadata={
                "webhook_event_id": str(event_id),
                "outcome": detail.processing_status,
                "provider": "stripe",
            },
            commit=True,
        )
        return detail


@router.post("/events/{event_id}/retry", response_model=WebhookEventDetail)
def retry_webhook_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> WebhookEventDetail:
    """Reopen a failed (or dismissed) event with a fresh retry cycle; history kept."""
    with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
        return webhook_event_service.retry(db, event_id, correlation_id=correlation_id)


@router.post("/events/{event_id}/dismiss", response_model=WebhookEventDetail)
def dismiss_webhook_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
) -> WebhookEventDetail:
    """Stop processing an event without deleting its history."""
    with correlation_scope(parse_correlation_id(x_correlation_id)) as correlation_id:
        return webhook_event_service.dismiss(db, event_id, correlation_id=correlation_id)
