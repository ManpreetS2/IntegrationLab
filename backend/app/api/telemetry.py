"""Universal telemetry ingestion and operator reads.

POST /events authenticates an ingestion credential. GET routes stay on the
operator gate. Neither path calls a third-party API.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ingestion_rate_limit import auth_failure_limiter, ingest_request_limiter
from app.core.operator_auth import extract_bearer_token
from app.db.models.telemetry import IngestionCredentialORM
from app.models.integration import IntegrationProvider
from app.models.telemetry import (
    ErrorCategory,
    IngestResponse,
    InstrumentedHealthResponse,
    TelemetryEventPage,
    TelemetryEventView,
)
from app.repositories.integrations import integration_repository
from app.repositories.telemetry import telemetry_repository
from app.services.ingestion_credentials import ingestion_credential_service, parse_credential
from app.services.reliability import DatabaseUnavailableError, database_unavailable, reliability_service
from app.services.telemetry_ingest import parse_batch, telemetry_ingest_service
from app.services.telemetry_limits import RATE_LIMIT_RETRY_AFTER_SECONDS
from app.services import reliability_rules as rules

router = APIRouter(prefix="/api/telemetry/v1", tags=["telemetry"])

_AUTH_HEADER = {"WWW-Authenticate": 'Bearer realm="integrationlab-ingestion"'}


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def _client_host(request: Request) -> str:
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Ingestion rate limit exceeded",
        headers={"Retry-After": str(RATE_LIMIT_RETRY_AFTER_SECONDS)},
    )


def require_ingestion_credential(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Annotated[str | None, Header()] = None,
) -> IngestionCredentialORM:
    host = _client_host(request)
    token = extract_bearer_token(authorization)
    prefix = parse_credential(token) if token else None
    failure_keys = [f"ip:{host}"]
    if prefix:
        failure_keys.append(f"prefix:{prefix}")

    def reject(detail: str) -> None:
        for key in failure_keys:
            if not auth_failure_limiter.allow(key):
                raise _rate_limited()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers=_AUTH_HEADER,
        )

    if not token:
        reject("Invalid ingestion credential")
    try:
        result = ingestion_credential_service.authenticate(db, token)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None
    if result.failure == "revoked":
        reject("Ingestion credential revoked")
    if result.credential is None:
        reject("Invalid ingestion credential")
    if not ingest_request_limiter.allow(f"integration:{result.credential.integration_id}"):
        raise _rate_limited()
    return result.credential


def _require_instrumented(db: Session, integration_id: UUID):
    integration = integration_repository.get_by_id(db, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    if integration.provider != IntegrationProvider.INSTRUMENTED_HTTP.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telemetry reads are only available for instrumented_http integrations",
        )
    return integration


def _aware(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise HTTPException(
            status_code=422,
            detail=f"{name} must include a timezone offset",
        )
    return value.astimezone(timezone.utc)


def encode_cursor(received_at: datetime, event_id: UUID) -> str:
    raw = f"{received_at.astimezone(timezone.utc).isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding).decode()
        stamp, event_id = decoded.split("|", 1)
        parsed = datetime.fromisoformat(stamp)
        if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
            raise ValueError
        return parsed.astimezone(timezone.utc), UUID(event_id)
    except (ValueError, UnicodeError, binascii.Error):
        raise HTTPException(
            status_code=422,
            detail="Invalid cursor",
        ) from None


@router.post("/events", response_model=IngestResponse)
def ingest_events(
    raw: Annotated[bytes, Depends(_raw_body)],
    db: Session = Depends(get_db),
    credential: IngestionCredentialORM = Depends(require_ingestion_credential),
) -> IngestResponse:
    """Accept a bounded batch of SDK-reported HTTP observations."""
    now = datetime.now(timezone.utc)
    try:
        batch = parse_batch(raw, now=now)
        result = telemetry_ingest_service.accept(
            db,
            credential_id=credential.id,
            events=batch.events,
            now=now,
        )
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.get("/events", response_model=TelemetryEventPage)
def list_events(
    integration_id: UUID,
    service: str | None = Query(default=None, max_length=63),
    status_code: int | None = Query(default=None, ge=200, le=599),
    error_category: ErrorCategory | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> TelemetryEventPage:
    """Page SDK-reported observations for one instrumented integration."""
    try:
        _require_instrumented(db, integration_id)
        cursor_received_at = None
        cursor_event_id = None
        if cursor:
            cursor_received_at, cursor_event_id = decode_cursor(cursor)
        rows = telemetry_repository.page(
            db,
            integration_id=integration_id,
            limit=limit + 1,
            cursor_received_at=cursor_received_at,
            cursor_event_id=cursor_event_id,
            service=service,
            status_code=status_code,
            error_category=error_category.value if error_category else None,
            occurred_after=_aware(occurred_after, "occurred_after"),
            occurred_before=_aware(occurred_before, "occurred_before"),
        )
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor(last.received_at, last.event_id)
    return TelemetryEventPage(
        items=[TelemetryEventView.model_validate(row) for row in page],
        next_cursor=next_cursor,
    )


@router.get("/integrations/{integration_id}/health", response_model=InstrumentedHealthResponse)
def instrumented_health(
    integration_id: UUID,
    window_hours: int = Query(
        default=rules.DEFAULT_WINDOW_HOURS,
        ge=rules.MIN_WINDOW_HOURS,
        le=rules.MAX_WINDOW_HOURS,
    ),
    db: Session = Depends(get_db),
) -> InstrumentedHealthResponse:
    """Evidence-backed health for SDK-reported observations. No outbound calls."""
    try:
        return reliability_service.instrumented_health(
            db, integration_id, window_hours=window_hours
        )
    except DatabaseUnavailableError:
        raise database_unavailable() from None
    except SQLAlchemyError:
        db.rollback()
        raise database_unavailable() from None
