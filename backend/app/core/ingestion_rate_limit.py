"""Process-local sliding-window limits for telemetry ingestion.

The current deployment is a single API process. This limiter does not coordinate
across machines. It is enough to bound accidental loops and local credential
guessing without adding Redis or another service.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from app.services.telemetry_limits import (
    AUTH_FAILURES_PER_WINDOW,
    INGEST_REQUESTS_PER_WINDOW,
    RATE_LIMIT_WINDOW_SECONDS,
)

# How often ``allow`` sweeps *all* keys for expired windows. Without this,
# distinct keys that never return keep their (stale) deque entries forever.
_DEFAULT_SWEEP_EVERY = 64


class SlidingWindowLimiter:
    """Allow up to ``limit`` hits per key inside ``window_seconds``."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        sweep_every: int = _DEFAULT_SWEEP_EVERY,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._sweep_every = max(1, sweep_every)
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self._ops_since_sweep = 0

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            self._ops_since_sweep += 1
            if self._ops_since_sweep >= self._sweep_every:
                self._sweep_expired(now)
                self._ops_since_sweep = 0

            hits = self._hits.setdefault(key, deque())
            self._prune_key(hits, now)
            if not hits:
                self._hits.pop(key, None)
            if len(hits) >= self.limit:
                return False
            if key not in self._hits:
                hits = deque()
                self._hits[key] = hits
            hits.append(now)
            return True

    def _prune_key(self, hits: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

    def _sweep_expired(self, now: float) -> None:
        dead: list[str] = []
        for key, hits in self._hits.items():
            self._prune_key(hits, now)
            if not hits:
                dead.append(key)
        for key in dead:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._ops_since_sweep = 0


auth_failure_limiter = SlidingWindowLimiter(
    AUTH_FAILURES_PER_WINDOW, RATE_LIMIT_WINDOW_SECONDS
)
ingest_request_limiter = SlidingWindowLimiter(
    INGEST_REQUESTS_PER_WINDOW, RATE_LIMIT_WINDOW_SECONDS
)


def reset_ingestion_rate_limits() -> None:
    """Clear in-process counters. Tests call this between cases."""
    auth_failure_limiter.limit = AUTH_FAILURES_PER_WINDOW
    auth_failure_limiter.window_seconds = RATE_LIMIT_WINDOW_SECONDS
    ingest_request_limiter.limit = INGEST_REQUESTS_PER_WINDOW
    ingest_request_limiter.window_seconds = RATE_LIMIT_WINDOW_SECONDS
    auth_failure_limiter.reset()
    ingest_request_limiter.reset()
