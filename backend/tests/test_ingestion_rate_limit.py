"""Sliding-window limiter behavior."""

from __future__ import annotations

from app.core.ingestion_rate_limit import SlidingWindowLimiter


def test_limiter_drops_empty_keys_on_reuse() -> None:
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60.0)
    assert limiter.allow("probe-a")
    limiter._hits["probe-a"].clear()
    assert limiter.allow("probe-a")
    assert len(limiter._hits) == 1
    assert len(limiter._hits["probe-a"]) == 1


def test_limiter_still_enforces_limit() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60.0)
    assert limiter.allow("same")
    assert limiter.allow("same")
    assert limiter.allow("same") is False
