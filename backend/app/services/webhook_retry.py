"""Deterministic retry policy for internal webhook processing.

Attempt semantics (per retry cycle):
    attempt 1 fails (retryable) -> retry in 1s
    attempt 2 fails (retryable) -> retry in 2s
    attempt 3 fails (retryable) -> retry in 4s
    attempt 4 fails (retryable) -> failed queue
So max_attempts=4 means 1 initial attempt + 3 retries.
Permanent errors never retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY_SECONDS = 1


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: int | None
    next_attempt_at: datetime | None


class WebhookRetryPolicy:
    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_seconds: int = DEFAULT_BASE_DELAY_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds

    def delay_for(self, failed_attempt_number: int) -> int:
        """Exponential backoff: 1, 2, 4, ... seconds after attempt 1, 2, 3, ..."""
        return self.base_delay_seconds * (2 ** (failed_attempt_number - 1))

    def decide(
        self,
        *,
        failed_attempt_number: int,
        retryable: bool,
        now: datetime,
        max_attempts: int | None = None,
    ) -> RetryDecision:
        limit = max_attempts if max_attempts is not None else self.max_attempts
        if not retryable or failed_attempt_number >= limit:
            return RetryDecision(should_retry=False, delay_seconds=None, next_attempt_at=None)
        delay = self.delay_for(failed_attempt_number)
        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            next_attempt_at=now + timedelta(seconds=delay),
        )


webhook_retry_policy = WebhookRetryPolicy()
