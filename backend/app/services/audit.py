"""Centralized operator audit trail writer with safe metadata allowlisting."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.correlation import get_correlation_id
from app.db.models.support import OperatorAuditEventORM

# Only these metadata keys may be persisted. Keep values scalars / short strings.
# Structural / enum / id fields only — never free-form operator text (title, name, notes).
_SAFE_METADATA_KEYS = frozenset(
    {
        "case_number",
        "status",
        "from_status",
        "to_status",
        "severity",
        "from_severity",
        "to_severity",
        "environment",
        "provider",
        "evidence_type",
        "evidence_id",
        "is_simulated",
        "scenario",
        "trigger",
        "outcome",
        "note_id",
        "webhook_event_id",
        "diagnostic_run_id",
        "failure_lab_run_id",
        "provider_request_id",
        "processed",
        "retry_scheduled",
        "failed",
        "ignored",
        "skipped",
        "limit",
    }
)

_BLOCKED_METADATA_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "apikey",
    "api_key",
    "bearer",
    "private_key",
    "encryption",
)


class AuditService:
    """Append-only audit events for meaningful operator ACTIONS."""

    def record(
        self,
        session: Session,
        *,
        action: str,
        target_type: str,
        safe_summary: str,
        outcome: str = "success",
        target_id: str | UUID | None = None,
        integration_id: UUID | None = None,
        support_case_id: UUID | None = None,
        correlation_id: UUID | None = None,
        metadata: Optional[dict[str, Any]] = None,
        actor_type: str = "operator",
        commit: bool = False,
    ) -> OperatorAuditEventORM:
        event = OperatorAuditEventORM(
            id=uuid4(),
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            integration_id=integration_id,
            support_case_id=support_case_id,
            correlation_id=correlation_id or get_correlation_id(),
            actor_type=actor_type,
            outcome=outcome,
            safe_summary=safe_summary[:500],
            metadata_json=sanitize_audit_metadata(metadata),
        )
        session.add(event)
        session.flush()
        if commit:
            session.commit()
            session.refresh(event)
        return event


def sanitize_audit_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any] | None:
    """Allowlist keys and drop anything that looks like a secret."""
    if not metadata:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in _SAFE_METADATA_KEYS:
            continue
        key_lower = key.lower()
        if any(blocked in key_lower for blocked in _BLOCKED_METADATA_SUBSTRINGS):
            continue
        if isinstance(value, (bool, int, float)):
            cleaned[key] = value
        elif isinstance(value, UUID):
            cleaned[key] = str(value)
        elif isinstance(value, str):
            lowered = value.lower()
            if any(blocked in lowered for blocked in _BLOCKED_METADATA_SUBSTRINGS):
                continue
            cleaned[key] = value[:200]
        elif value is None:
            continue
        else:
            cleaned[key] = str(value)[:200]
    return cleaned or None


audit_service = AuditService()
