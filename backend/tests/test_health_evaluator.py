"""Pure unit tests for deterministic health rules (no DB, no network)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.reliability import HealthState, LatencyBand, RequestMetrics, WebhookMetrics
from app.services.health_evaluator import (
    GitHubEvidence,
    StripeEvidence,
    evaluate_github,
    evaluate_stripe,
)
from app.services.reliability_rules import latency_band

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _metrics(**overrides) -> RequestMetrics:
    base = dict(
        request_count=1,
        success_count=1,
        failure_count=0,
        error_rate=0.0,
        average_latency_ms=120,
        p95_latency_ms=120,
        latest_latency_ms=120,
        latest_latency_band=LatencyBand.NORMAL,
        latest_status_code=200,
        latest_error_code=None,
        latest_endpoint="/user",
        latest_request_at=NOW,
        rate_limit_remaining=4990,
    )
    base.update(overrides)
    return RequestMetrics(**base)


def _github(status="connected", *, credential=True, metrics=None, last_activity=None) -> GitHubEvidence:
    return GitHubEvidence(
        connection_status=status,
        has_credential=credential,
        metrics=metrics if metrics is not None else _metrics(),
        window_hours=24,
        last_activity_at=last_activity,
    )


def _failed(code: str | None, status: int | None, **kw) -> RequestMetrics:
    return _metrics(
        success_count=0, failure_count=1, error_rate=1.0,
        latest_status_code=status, latest_error_code=code, **kw,
    )


# ------------------------------------------------------------------ GitHub


def test_github_not_connected_is_not_configured():
    result = evaluate_github(_github("not_connected", credential=False, metrics=RequestMetrics()))
    assert result.health == HealthState.NOT_CONFIGURED
    assert result.recommended_action


def test_github_needs_setup_is_failed():
    result = evaluate_github(_github("needs_setup"))
    assert result.health == HealthState.FAILED
    assert "Reconnect GitHub" in result.recommended_action


def test_github_connected_without_evidence_is_unknown_not_healthy():
    result = evaluate_github(_github(metrics=RequestMetrics()))
    assert result.health == HealthState.UNKNOWN
    assert "no recent real GitHub request evidence" in result.summary


def test_github_unknown_mentions_older_evidence_outside_window():
    result = evaluate_github(_github(metrics=RequestMetrics(), last_activity=NOW))
    assert any("outside the selected window" in line for line in result.evidence)


def test_github_connected_with_recent_200_is_healthy():
    result = evaluate_github(_github())
    assert result.health == HealthState.HEALTHY
    assert "Latest real /user request: HTTP 200." in result.evidence
    assert "0 / 1 real requests failed in the last 24h." in result.evidence


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("github_timeout", None),
        ("github_transport_error", None),
        ("github_server_error", 500),
        ("github_server_error", 503),
        ("github_rate_limited", 429),
        ("github_rate_limited", 403),
        ("github_forbidden", 403),
    ],
)
def test_github_recent_provider_failures_are_degraded(code, status):
    result = evaluate_github(_github(metrics=_failed(code, status)))
    assert result.health == HealthState.DEGRADED


def test_github_timeout_wording_does_not_claim_outage():
    result = evaluate_github(_github(metrics=_failed("github_timeout", None)))
    assert result.summary == "GitHub request timed out."
    assert "down" not in result.summary.lower()


def test_github_recent_401_is_failed():
    result = evaluate_github(_github(metrics=_failed("github_unauthorized", 401)))
    assert result.health == HealthState.FAILED
    assert "401" in result.summary


def test_github_single_failure_reports_sample_size_not_percentage():
    result = evaluate_github(_github(metrics=_failed("github_server_error", 500)))
    assert "1 / 1 real requests failed in the last 24h." in result.evidence
    assert not any("%" in line for line in result.evidence)


def test_github_repeated_failures_degrade_even_if_latest_succeeded():
    metrics = _metrics(request_count=10, success_count=7, failure_count=3, error_rate=0.3)
    result = evaluate_github(_github(metrics=metrics))
    assert result.health == HealthState.DEGRADED
    assert "3 / 10" in result.summary


def test_github_one_old_failure_among_many_successes_stays_healthy():
    metrics = _metrics(request_count=10, success_count=9, failure_count=1, error_rate=0.1)
    assert evaluate_github(_github(metrics=metrics)).health == HealthState.HEALTHY


def test_github_error_rate_needs_minimum_sample():
    # 1 failure of 2 = 50%, but below the sample and repeat thresholds.
    metrics = _metrics(request_count=2, success_count=1, failure_count=1, error_rate=0.5)
    assert evaluate_github(_github(metrics=metrics)).health == HealthState.HEALTHY


def test_github_slow_latency_is_degraded_not_failed():
    metrics = _metrics(latest_latency_ms=2400, latest_latency_band=LatencyBand.SLOW)
    result = evaluate_github(_github(metrics=metrics))
    assert result.health == HealthState.DEGRADED
    assert "2400ms" in result.summary


def test_github_elevated_latency_stays_healthy():
    metrics = _metrics(latest_latency_ms=900, latest_latency_band=LatencyBand.ELEVATED)
    assert evaluate_github(_github(metrics=metrics)).health == HealthState.HEALTHY


def test_github_low_rate_limit_is_degraded():
    result = evaluate_github(_github(metrics=_metrics(rate_limit_remaining=12)))
    assert result.health == HealthState.DEGRADED


def test_github_connected_but_credential_missing_is_failed():
    assert evaluate_github(_github(credential=False)).health == HealthState.FAILED


def test_latency_bands():
    assert latency_band(None) is None
    assert latency_band(120) == LatencyBand.NORMAL
    assert latency_band(500) == LatencyBand.ELEVATED
    assert latency_band(1500) == LatencyBand.ELEVATED
    assert latency_band(1501) == LatencyBand.SLOW


# ------------------------------------------------------------------ Stripe


def _webhooks(**overrides) -> WebhookMetrics:
    base = dict(verification_configured=True, events_total=3, events_in_window=3, processed=3)
    base.update(overrides)
    return WebhookMetrics(**base)


def _stripe(metrics: WebhookMetrics) -> StripeEvidence:
    return StripeEvidence(metrics=metrics, window_hours=24)


def test_stripe_secret_missing_is_not_configured():
    result = evaluate_stripe(_stripe(WebhookMetrics(verification_configured=False)))
    assert result.health == HealthState.NOT_CONFIGURED
    assert result.summary == "Stripe webhook verification secret is not configured."


def test_stripe_secret_missing_with_prior_events_explains_503():
    result = evaluate_stripe(_stripe(_webhooks(verification_configured=False)))
    assert result.health == HealthState.NOT_CONFIGURED
    assert any("503" in line for line in result.evidence)


def test_stripe_configured_without_events_is_unknown():
    result = evaluate_stripe(_stripe(WebhookMetrics(verification_configured=True)))
    assert result.health == HealthState.UNKNOWN
    assert "no verified Stripe deliveries" in result.summary


def test_stripe_clean_processing_is_healthy():
    result = evaluate_stripe(_stripe(_webhooks(ignored=1, events_total=4, events_in_window=4)))
    assert result.health == HealthState.HEALTHY


def test_stripe_no_recent_deliveries_is_still_healthy_but_says_so():
    result = evaluate_stripe(_stripe(_webhooks(events_in_window=0)))
    assert result.health == HealthState.HEALTHY
    assert "no deliveries in the last 24h" in result.summary


def test_stripe_retry_scheduled_is_degraded():
    result = evaluate_stripe(_stripe(_webhooks(retry_scheduled=2)))
    assert result.health == HealthState.DEGRADED
    assert "waiting to retry" in result.summary


def test_stripe_failed_queue_is_degraded_not_failed():
    result = evaluate_stripe(_stripe(_webhooks(failed=1)))
    assert result.health == HealthState.DEGRADED
    assert result.recommended_action == "Open Failed Events and inspect the latest processing attempt."


def test_stripe_duplicates_alone_do_not_degrade():
    result = evaluate_stripe(_stripe(_webhooks(duplicate_deliveries=25)))
    assert result.health == HealthState.HEALTHY
    assert any("duplicate deliveries absorbed" in line for line in result.evidence)


def test_stripe_stale_processing_is_degraded():
    result = evaluate_stripe(_stripe(_webhooks(processing=1, stale_processing=1)))
    assert result.health == HealthState.DEGRADED
    assert "reclaims" in result.recommended_action


def test_stripe_stale_pending_is_degraded_fresh_pending_is_not():
    assert evaluate_stripe(_stripe(_webhooks(pending=2))).health == HealthState.HEALTHY
    stale = evaluate_stripe(_stripe(_webhooks(pending=2, stale_pending=2)))
    assert stale.health == HealthState.DEGRADED
    assert "verify pending events are being claimed" in stale.recommended_action


def test_evaluation_is_deterministic():
    ev = _github(metrics=_failed("github_timeout", None))
    assert evaluate_github(ev) == evaluate_github(ev)
