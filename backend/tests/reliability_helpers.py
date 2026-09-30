"""Helpers for seeding reliability evidence directly (controlled timestamps, no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import TokenCipher
from app.db.models.integration import IntegrationORM
from app.db.models.oauth import OAuthCredentialORM, ProviderRequestLogORM
from app.db.models.webhook import WebhookEventORM, WebhookProcessingAttemptORM

FAKE_TOKEN = "gho_example_reliability_token"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def github_integration(session: Session, name: str = "GitHub") -> IntegrationORM:
    integration = session.query(IntegrationORM).filter_by(provider="github", name=name).first()
    assert integration is not None
    return integration


def connect_github_directly(
    session: Session,
    integration_id: UUID,
    *,
    scopes: str | None = "read:user",
    ciphertext: str | None = None,
) -> str:
    """Mark connected and store an encrypted fake token. Returns the stored ciphertext."""
    integration = session.get(IntegrationORM, integration_id)
    assert integration is not None
    integration.status = "connected"
    encrypted = ciphertext if ciphertext is not None else TokenCipher().encrypt(FAKE_TOKEN)
    session.add(
        OAuthCredentialORM(
            integration_id=integration_id,
            provider="github",
            access_token_encrypted=encrypted,
            token_type="bearer",
            granted_scopes=scopes,
        )
    )
    session.commit()
    return encrypted


def add_log(
    session: Session,
    integration_id: UUID | None,
    *,
    status_code: int | None = 200,
    latency_ms: int = 120,
    error: str | None = None,
    simulated: bool = False,
    at: datetime | None = None,
    endpoint: str = "/user",
    provider: str = "github",
    rate_limit_remaining: int | None = 4900,
) -> ProviderRequestLogORM:
    row = ProviderRequestLogORM(
        integration_id=integration_id,
        provider=provider,
        method="GET",
        endpoint=endpoint,
        status_code=status_code,
        latency_ms=latency_ms,
        timestamp=at or utcnow(),
        error_message=error,
        rate_limit_remaining=rate_limit_remaining,
        is_simulated=simulated,
        scenario="provider_500" if simulated else None,
    )
    session.add(row)
    session.commit()
    return row


def set_event_state(
    session: Session,
    event: WebhookEventORM,
    *,
    status: str,
    error_code: str | None = None,
    processing_started_at: datetime | None = None,
    first_received_at: datetime | None = None,
) -> WebhookEventORM:
    now = utcnow()
    event = session.get(WebhookEventORM, event.id)
    assert event is not None
    event.processing_status = status
    if status == "failed":
        event.failed_at = now
        event.attempt_count = 4
    if status == "retry_scheduled":
        event.next_attempt_at = now + timedelta(minutes=5)
        event.attempt_count = 1
    if status == "processed":
        event.processed_at = now
    if error_code:
        event.last_error_code = error_code
        event.last_error_message = "Simulated handler error for tests."
    if processing_started_at is not None:
        event.processing_started_at = processing_started_at
    if first_received_at is not None:
        event.first_received_at = first_received_at
        event.last_received_at = first_received_at
    session.commit()
    return event


def add_attempt(
    session: Session,
    event: WebhookEventORM,
    *,
    outcome: str,
    number: int = 1,
    error_code: str | None = None,
    at: datetime | None = None,
    retry_delay_seconds: int | None = None,
) -> None:
    """outcome is one of succeeded / ignored / failed / abandoned."""
    started = at or utcnow()
    session.add(
        WebhookProcessingAttemptORM(
            webhook_event_id=event.id,
            attempt_number=number,
            retry_cycle=1,
            cycle_attempt_number=number,
            started_at=started,
            finished_at=started,
            outcome=outcome,
            error_code=error_code,
            retryable=retry_delay_seconds is not None,
            scheduled_delay_seconds=retry_delay_seconds,
        )
    )
    session.commit()
