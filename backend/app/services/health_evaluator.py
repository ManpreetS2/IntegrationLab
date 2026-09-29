"""Deterministic integration health rules.

Pure functions: an evidence snapshot goes in, a health assessment comes out.
No database, no network, no clock. Rules are evaluated top-down; the first
matching rule decides the state, and evidence lines explain why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.integration import IntegrationStatus
from app.models.reliability import HealthState, LatencyBand, RequestMetrics, WebhookMetrics
from app.services import reliability_rules as rules


@dataclass(frozen=True)
class HealthAssessment:
    health: HealthState
    summary: str
    evidence: list[str] = field(default_factory=list)
    recommended_action: str | None = None


@dataclass(frozen=True)
class GitHubEvidence:
    connection_status: str
    has_credential: bool
    metrics: RequestMetrics
    window_hours: int
    last_activity_at: datetime | None = None


@dataclass(frozen=True)
class StripeEvidence:
    metrics: WebhookMetrics
    window_hours: int


RECONNECT_GITHUB = "Reconnect GitHub to replace the stored OAuth credential."
COLLECT_GITHUB_EVIDENCE = "Run diagnostics (or Check connection) to collect a current GitHub check."

_GITHUB_FAILURE_ACTIONS = {
    "github_rate_limited": "Review remaining quota and wait for the provider reset window before retrying.",
    "github_timeout": "Retry the check later; if timeouts persist, check network connectivity to api.github.com.",
    "github_transport_error": "Check network/DNS connectivity to api.github.com, then retry the check.",
    "github_server_error": "Check githubstatus.com and retry later; this evidence does not indicate a credential problem.",
    "github_forbidden": "Confirm the granted OAuth scopes cover the requested resource.",
    "github_malformed_json": "Retry the check; the provider response body was not valid JSON.",
}


def _request_evidence(m: RequestMetrics, window_hours: int) -> list[str]:
    lines: list[str] = []
    if m.latest_request_at is not None:
        status = f"HTTP {m.latest_status_code}" if m.latest_status_code is not None else "no HTTP response"
        endpoint = m.latest_endpoint or "request"
        suffix = f" ({m.latest_error_code})" if m.latest_error_code else ""
        lines.append(f"Latest real {endpoint} request: {status}{suffix}.")
    if m.latest_latency_ms is not None and m.latest_latency_band is not None:
        lines.append(f"Latest observed latency: {m.latest_latency_ms}ms ({m.latest_latency_band.value}).")
    if m.request_count:
        if m.failure_count:
            lines.append(
                f"{m.failure_count} / {m.request_count} real requests failed in the last {window_hours}h."
            )
        else:
            lines.append(f"0 / {m.request_count} real requests failed in the last {window_hours}h.")
    if m.rate_limit_remaining is not None:
        lines.append(f"Rate limit remaining: {m.rate_limit_remaining}.")
    return lines


def evaluate_github(ev: GitHubEvidence) -> HealthAssessment:
    m = ev.metrics
    w = ev.window_hours

    if ev.connection_status == IntegrationStatus.NOT_CONNECTED.value:
        return HealthAssessment(
            HealthState.NOT_CONFIGURED,
            "GitHub is not connected.",
            ["Integration status is not_connected; no OAuth credential is in use."],
            "Connect GitHub to start collecting real request evidence.",
        )

    if ev.connection_status == IntegrationStatus.NEEDS_SETUP.value:
        return HealthAssessment(
            HealthState.FAILED,
            "GitHub credential needs attention.",
            [
                "Integration status is needs_setup: an earlier authenticated request was rejected.",
                *_request_evidence(m, w),
            ],
            RECONNECT_GITHUB,
        )

    if not ev.has_credential:
        return HealthAssessment(
            HealthState.FAILED,
            "GitHub is marked connected, but no stored credential was found.",
            ["No encrypted OAuth credential exists for this integration."],
            RECONNECT_GITHUB,
        )

    if m.request_count == 0:
        evidence = [f"No real GitHub requests in the last {w}h."]
        if ev.last_activity_at is not None:
            evidence.append("Older real requests exist outside the selected window.")
        return HealthAssessment(
            HealthState.UNKNOWN,
            "Connected, but there is no recent real GitHub request evidence.",
            evidence,
            COLLECT_GITHUB_EVIDENCE,
        )

    evidence = _request_evidence(m, w)

    if m.latest_status_code == 401 or m.latest_error_code == "github_unauthorized":
        return HealthAssessment(
            HealthState.FAILED,
            "Latest real GitHub request was rejected as unauthorized (HTTP 401).",
            evidence,
            RECONNECT_GITHUB,
        )

    if m.latest_error_code:
        return HealthAssessment(
            HealthState.DEGRADED,
            rules.provider_failure_summary("github", m.latest_error_code, m.latest_status_code),
            evidence,
            _GITHUB_FAILURE_ACTIONS.get(m.latest_error_code, COLLECT_GITHUB_EVIDENCE),
        )

    repeated = m.failure_count >= rules.REPEATED_FAILURES_DEGRADED
    high_rate = (
        m.request_count >= rules.MIN_SAMPLE_FOR_ERROR_RATE
        and m.error_rate is not None
        and m.error_rate >= rules.ERROR_RATE_DEGRADED
    )
    if repeated or high_rate:
        return HealthAssessment(
            HealthState.DEGRADED,
            f"Latest request succeeded, but {m.failure_count} / {m.request_count} real requests "
            f"failed in the last {w}h.",
            evidence,
            "Open Failures to review the recent GitHub errors before relying on this connection.",
        )

    if m.latest_latency_band == LatencyBand.SLOW:
        return HealthAssessment(
            HealthState.DEGRADED,
            f"Latest real GitHub request was slow ({m.latest_latency_ms}ms; local threshold "
            f"{rules.LATENCY_SLOW_MS}ms).",
            evidence,
            "Re-run diagnostics to see whether latency stays above the local threshold.",
        )

    if m.rate_limit_remaining is not None and m.rate_limit_remaining < rules.RATE_LIMIT_LOW_REMAINING:
        return HealthAssessment(
            HealthState.DEGRADED,
            f"GitHub rate limit is nearly exhausted ({m.rate_limit_remaining} remaining).",
            evidence,
            "Review remaining quota and wait for the provider reset window before retrying.",
        )

    return HealthAssessment(
        HealthState.HEALTHY,
        "GitHub connection is responding normally.",
        evidence,
        None,
    )


def evaluate_stripe(ev: StripeEvidence) -> HealthAssessment:
    m = ev.metrics
    w = ev.window_hours

    if not m.verification_configured:
        evidence = ["Stripe webhook verification secret is not configured."]
        if m.events_total:
            evidence.append(
                f"{m.events_total} events were received earlier; new deliveries are rejected "
                "with HTTP 503 until the secret is configured."
            )
        return HealthAssessment(
            HealthState.NOT_CONFIGURED,
            "Stripe webhook verification secret is not configured.",
            evidence,
            "Set STRIPE_WEBHOOK_SECRET in the backend environment and restart the API.",
        )

    if m.events_total == 0:
        return HealthAssessment(
            HealthState.UNKNOWN,
            "Webhook verification is configured, but no verified Stripe deliveries have been observed.",
            ["0 signature-verified webhook events stored for this integration."],
            "Forward a test event (stripe listen + stripe trigger) and confirm it is received.",
        )

    evidence = [
        f"{m.events_total} verified events stored ({m.events_in_window} in the last {w}h).",
        f"Current states: {m.processed} processed, {m.ignored} ignored, {m.pending} pending, "
        f"{m.retry_scheduled} retry scheduled, {m.failed} failed.",
    ]
    if m.duplicate_deliveries:
        evidence.append(
            f"{m.duplicate_deliveries} duplicate deliveries absorbed (expected under at-least-once delivery)."
        )

    problems: list[str] = []
    if m.failed:
        problems.append(f"{m.failed} event(s) in the failed queue")
    if m.retry_scheduled:
        problems.append(f"{m.retry_scheduled} event(s) waiting to retry")
    if m.stale_processing:
        problems.append(
            f"{m.stale_processing} event(s) stuck in processing for over {rules.STALE_PROCESSING_MINUTES} min"
        )
    if m.stale_pending:
        problems.append(
            f"{m.stale_pending} pending event(s) unprocessed for over {rules.STALE_PENDING_MINUTES} min"
        )

    if problems:
        if m.failed:
            action = "Open Failed Events and inspect the latest processing attempt."
        elif m.stale_processing:
            action = (
                "Run the webhook processor; it reclaims processing rows older than "
                f"{rules.STALE_PROCESSING_MINUTES} minutes."
            )
        else:
            action = "Run the webhook processor and verify pending events are being claimed."
        return HealthAssessment(
            HealthState.DEGRADED,
            "Webhook processing needs attention: " + "; ".join(problems) + ".",
            evidence + [p[0].upper() + p[1:] + "." for p in problems],
            action,
        )

    if m.pending:
        evidence.append(f"{m.pending} recently received event(s) awaiting processing.")
    summary = (
        "Verified webhooks are being received and processed."
        if m.events_in_window
        else f"All received webhooks are processed; no deliveries in the last {w}h."
    )
    return HealthAssessment(HealthState.HEALTHY, summary, evidence, None)
