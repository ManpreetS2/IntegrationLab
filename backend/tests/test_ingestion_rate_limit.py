"""Sliding-window limiter behavior."""

from __future__ import annotations

from app.core.ingestion_rate_limit import SlidingWindowLimiter


def test_limiter_still_enforces_limit() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60.0)
    assert limiter.allow("same")
    assert limiter.allow("same")
    assert limiter.allow("same") is False


def test_limiter_sweeps_stale_keys_without_reuse() -> None:
    """Distinct prefixes that never return must not accumulate forever."""
    clock = {"t": 1_000.0}

    def now() -> float:
        return clock["t"]

    limiter = SlidingWindowLimiter(
        limit=5,
        window_seconds=10.0,
        sweep_every=1,
        clock=now,
    )
    for i in range(200):
        assert limiter.allow(f"prefix-{i}")
    assert len(limiter._hits) == 200

    clock["t"] += 11.0
    assert limiter.allow("fresh")
    assert "prefix-0" not in limiter._hits
    assert "prefix-199" not in limiter._hits
    assert list(limiter._hits) == ["fresh"]


def test_limiter_drops_empty_key_on_reuse() -> None:
    clock = {"t": 1_000.0}
    limiter = SlidingWindowLimiter(
        limit=5,
        window_seconds=10.0,
        sweep_every=10_000,
        clock=lambda: clock["t"],
    )
    assert limiter.allow("probe-a")
    clock["t"] += 11.0
    assert limiter.allow("probe-a")
    assert len(limiter._hits) == 1
    assert len(limiter._hits["probe-a"]) == 1
