"""Shared validation for timezone-aware datetime query parameters."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException


def require_timezone_aware(value: datetime | None, name: str) -> datetime | None:
    """Reject naive datetimes (consistent with telemetry list filters)."""
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise HTTPException(
            status_code=422,
            detail=f"{name} must include a timezone offset",
        )
    return value.astimezone(timezone.utc)
