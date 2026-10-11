"""Validate and persist a batch of SDK-reported HTTP observations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models.telemetry import IngestionCredentialORM
from app.models.telemetry import (
    IngestEventResult,
    IngestResponse,
    TelemetryBatch,
    TelemetryEventIn,
)
from app.repositories.telemetry import telemetry_repository
from app.services.telemetry_limits import MAX_EVENT_AGE, MAX_FUTURE_SKEW

def public_validation_errors(exc: ValidationError) -> dict[str, Any]:
    """Field errors without echoing submitted values."""
    errors = []
    for err in exc.errors()[:50]:
        errors.append(
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "Invalid value")),
                "type": str(err.get("type", "value_error")),
            }
        )
    return {"message": "Invalid telemetry payload", "errors": errors}


def parse_batch(payload: bytes, *, now: datetime) -> TelemetryBatch:
    if not payload:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Invalid telemetry payload",
                "errors": [{"loc": [], "msg": "Request body is empty", "type": "empty"}],
            },
        )
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON",
        ) from None
    try:
        batch = TelemetryBatch.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=public_validation_errors(exc),
        ) from None

    skew_errors = []
    earliest = now - MAX_EVENT_AGE
    latest = now + MAX_FUTURE_SKEW
    for index, event in enumerate(batch.events):
        if event.occurred_at < earliest or event.occurred_at > latest:
            skew_errors.append(
                {
                    "loc": ["events", index, "occurred_at"],
                    "msg": "occurred_at is outside the allowed window (24h past, 5m future)",
                    "type": "skew",
                }
            )
    if skew_errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid telemetry payload", "errors": skew_errors},
        )
    return batch


class TelemetryIngestService:
    def accept(
        self,
        session: Session,
        *,
        credential_id: UUID,
        events: list[TelemetryEventIn],
        now: datetime | None = None,
    ) -> IngestResponse:
        received_at = now or datetime.now(timezone.utc)
        credential = session.get(IngestionCredentialORM, credential_id, with_for_update=True)
        if credential is None or credential.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ingestion credential revoked",
                headers={"WWW-Authenticate": 'Bearer realm="integrationlab-ingestion"'},
            )
        if any(event.integration_id != credential.integration_id for event in events):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Event integration_id does not match the ingestion credential",
            )

        first_indexes: dict[UUID, int] = {}
        rows: list[dict] = []
        for index, event in enumerate(events):
            if event.event_id in first_indexes:
                continue
            first_indexes[event.event_id] = index
            rows.append(_row(event, credential_id=credential.id, received_at=received_at))

        inserted = telemetry_repository.insert_new(session, rows)
        credential.last_used_at = received_at
        session.add(credential)
        session.flush()

        results: list[IngestEventResult] = []
        accepted = 0
        duplicates = 0
        seen: set[UUID] = set()
        for event in events:
            if event.event_id in seen or event.event_id not in inserted:
                disposition = "duplicate"
                duplicates += 1
            else:
                disposition = "accepted"
                accepted += 1
            seen.add(event.event_id)
            results.append(IngestEventResult(event_id=event.event_id, disposition=disposition))

        return IngestResponse(
            integration_id=credential.integration_id,
            accepted=accepted,
            duplicates=duplicates,
            results=results,
        )


def _row(event: TelemetryEventIn, *, credential_id: UUID, received_at: datetime) -> dict:
    return {
        "id": uuid4(),
        "event_id": event.event_id,
        "integration_id": event.integration_id,
        "credential_id": credential_id,
        "occurred_at": event.occurred_at,
        "received_at": received_at,
        "kind": event.kind.value,
        "service": event.service,
        "method": event.method.value,
        "route_template": event.route_template,
        "status_code": event.status_code,
        "duration_ms": event.duration_ms,
        "error_category": event.error_category.value if event.error_category else None,
        "environment": event.environment.value,
        "provenance": event.provenance.value,
        "sdk_name": event.sdk.name if event.sdk else None,
        "sdk_version": event.sdk.version if event.sdk else None,
    }


telemetry_ingest_service = TelemetryIngestService()
