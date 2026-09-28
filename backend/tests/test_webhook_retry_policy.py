"""Deterministic retry policy (no sleeping, injectable now)."""

from datetime import datetime, timedelta, timezone

from app.services.webhook_retry import WebhookRetryPolicy

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_backoff_is_1_2_4_seconds():
    policy = WebhookRetryPolicy()
    assert [policy.delay_for(n) for n in (1, 2, 3)] == [1, 2, 4]


def test_retryable_failures_schedule_next_attempt():
    policy = WebhookRetryPolicy()
    for attempt, delay in ((1, 1), (2, 2), (3, 4)):
        decision = policy.decide(failed_attempt_number=attempt, retryable=True, now=NOW)
        assert decision.should_retry is True
        assert decision.delay_seconds == delay
        assert decision.next_attempt_at == NOW + timedelta(seconds=delay)


def test_fourth_failed_attempt_exhausts_budget():
    decision = WebhookRetryPolicy().decide(failed_attempt_number=4, retryable=True, now=NOW)
    assert decision.should_retry is False
    assert decision.next_attempt_at is None
    assert decision.delay_seconds is None


def test_permanent_errors_never_retry():
    decision = WebhookRetryPolicy().decide(failed_attempt_number=1, retryable=False, now=NOW)
    assert decision.should_retry is False


def test_per_event_max_attempts_override():
    policy = WebhookRetryPolicy()
    assert policy.decide(failed_attempt_number=2, retryable=True, now=NOW, max_attempts=2).should_retry is False
    assert policy.decide(failed_attempt_number=1, retryable=True, now=NOW, max_attempts=2).should_retry is True


def test_policy_is_configurable():
    policy = WebhookRetryPolicy(max_attempts=6, base_delay_seconds=3)
    assert [policy.delay_for(n) for n in (1, 2, 3, 4, 5)] == [3, 6, 12, 24, 48]
    assert policy.decide(failed_attempt_number=5, retryable=True, now=NOW).should_retry is True
    assert policy.decide(failed_attempt_number=6, retryable=True, now=NOW).should_retry is False
