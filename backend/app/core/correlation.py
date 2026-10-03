"""Request-scoped correlation IDs for operator actions and evidence.

Design:
- Generate a UUID at mutation entry points (or accept a valid UUID from
  ``X-Correlation-ID``).
- Store the active ID in a ContextVar for nested service calls.
- Never invent OpenTelemetry infrastructure; IDs are opaque and secret-free.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections.abc import Iterator
from typing import Optional
from uuid import UUID, uuid4

_CORRELATION_ID: ContextVar[UUID | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> UUID:
    """Create a fresh correlation UUID."""
    return uuid4()


def parse_correlation_id(raw: str | None) -> UUID | None:
    """Accept only well-formed UUID strings; reject arbitrary caller text."""
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def get_correlation_id() -> UUID | None:
    """Return the active correlation ID for this context, if any."""
    return _CORRELATION_ID.get()


def require_correlation_id() -> UUID:
    """Return the active ID or create and bind a new one."""
    current = _CORRELATION_ID.get()
    if current is not None:
        return current
    generated = new_correlation_id()
    _CORRELATION_ID.set(generated)
    return generated


def set_correlation_id(value: UUID) -> Token:
    """Bind a correlation ID for the current context. Returns a reset token."""
    return _CORRELATION_ID.set(value)


def reset_correlation_id(token: Token) -> None:
    """Reset the ContextVar using a token from :func:`set_correlation_id`."""
    _CORRELATION_ID.reset(token)


@contextmanager
def correlation_scope(correlation_id: Optional[UUID] = None) -> Iterator[UUID]:
    """Bind a correlation ID for a block (generate one when not provided)."""
    bound = correlation_id or new_correlation_id()
    token = set_correlation_id(bound)
    try:
        yield bound
    finally:
        reset_correlation_id(token)


def short_correlation_id(value: UUID | None) -> str | None:
    """Compact display form for UI (full UUID remains copyable separately)."""
    if value is None:
        return None
    text = str(value).replace("-", "")
    return f"corr_{text[:4]}…"


def short_entity_id(value: UUID | str) -> str:
    """Short, non-secret reference for audit summaries (not free-form text)."""
    text = str(value).replace("-", "")
    return text[:8]
