"""Deterministic Stripe webhook diagnostic checks.

No outbound Stripe API calls: this project has no Stripe secret API key, so
diagnostics only inspect webhook verification config and persisted receipt /
processing evidence. They never retry, dismiss, or modify webhook events.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.integration import IntegrationORM
from app.models.diagnostics import CheckStatus
from app.repositories.reliability import reliability_repository
from app.services import reliability_rules as rules
from app.services.diagnostic_checks import CheckResult
from app.services.reliability import build_webhook_metrics

PASS, WARNING, FAIL, UNKNOWN = CheckStatus.PASS, CheckStatus.WARNING, CheckStatus.FAIL, CheckStatus.UNKNOWN

RUN_PROCESSOR = (
    "Run the webhook processor (python -m app.scripts.process_webhooks or 'Process due events') "
    "and verify pending events are being claimed."
)


def run_stripe_checks(
    session: Session,
    integration: IntegrationORM,
    *,
    settings: Settings,
    now: datetime,
    window_hours: int = rules.DEFAULT_WINDOW_HOURS,
) -> list[CheckResult]:
    since = now - timedelta(hours=window_hours)
    aggregate = reliability_repository.webhook_aggregates(
        session,
        since=since,
        now=now,
        stale_processing_after=timedelta(minutes=rules.STALE_PROCESSING_MINUTES),
        stale_pending_after=timedelta(minutes=rules.STALE_PENDING_MINUTES),
    ).get(integration.id)
    attempts = reliability_repository.attempt_aggregates(session, since=since).get(integration.id)
    configured = bool(settings.stripe_webhook_secret)
    m = build_webhook_metrics(configured, aggregate, attempts)
    w = window_hours
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            "stripe_webhook_secret",
            "Webhook verification secret",
            PASS if configured else FAIL,
            "STRIPE_WEBHOOK_SECRET is configured (one environment-level secret; value not displayed)."
            if configured
            else "STRIPE_WEBHOOK_SECRET is not configured; deliveries are rejected with HTTP 503.",
            None if configured else "Set STRIPE_WEBHOOK_SECRET in the backend environment and restart the API.",
            required=True,
        )
    )

    if m.events_total:
        last = m.last_received_at.strftime("%Y-%m-%d %H:%M UTC") if m.last_received_at else "unknown"
        receipts = CheckResult(
            "stripe_verified_receipts",
            "Verified webhook receipts",
            PASS,
            f"{m.events_total} signature-verified events stored ({m.events_in_window} in the last {w}h); "
            f"latest delivery {last}.",
        )
    else:
        receipts = CheckResult(
            "stripe_verified_receipts",
            "Verified webhook receipts",
            UNKNOWN,
            "No signature-verified webhook deliveries have been observed for this integration.",
            "Forward a test event (stripe listen --forward-to ... then stripe trigger payment_intent.succeeded).",
        )
    receipts.required = True
    checks.append(receipts)

    checks.append(
        CheckResult(
            "stripe_duplicate_deliveries",
            "Duplicate deliveries",
            PASS,
            f"{m.duplicate_deliveries} duplicate deliveries absorbed by event-id dedupe "
            "(expected under at-least-once delivery)."
            if m.duplicate_deliveries
            else "No duplicate deliveries observed.",
        )
    )

    backlog_problem = m.stale_pending or m.retry_scheduled
    checks.append(
        CheckResult(
            "stripe_processing_backlog",
            "Processing backlog",
            WARNING if backlog_problem else PASS,
            f"Pending: {m.pending} ({m.stale_pending} older than {rules.STALE_PENDING_MINUTES} min); "
            f"retry scheduled: {m.retry_scheduled}; processing: {m.processing}.",
            RUN_PROCESSOR if backlog_problem else None,
        )
    )

    checks.append(
        CheckResult(
            "stripe_failed_queue",
            "Failed queue",
            FAIL if m.failed else PASS,
            f"{m.failed} event(s) are currently in the failed queue." if m.failed else "No events in the failed queue.",
            "Open Failed Events and inspect the latest processing attempt." if m.failed else None,
        )
    )

    checks.append(
        CheckResult(
            "stripe_stale_processing",
            "Stale processing",
            WARNING if m.stale_processing else PASS,
            f"{m.stale_processing} event(s) have been processing for over {rules.STALE_PROCESSING_MINUTES} minutes."
            if m.stale_processing
            else f"No events stuck in processing (threshold {rules.STALE_PROCESSING_MINUTES} min).",
            "Run the webhook processor; it reclaims stale processing rows and records them as abandoned."
            if m.stale_processing
            else None,
        )
    )

    succeeded, failed_attempts = m.successful_attempts_in_window, m.failed_attempts_in_window
    if succeeded == 0 and failed_attempts == 0:
        outcomes = CheckResult(
            "stripe_processing_outcomes",
            "Recent processing outcomes",
            UNKNOWN,
            f"No processing attempts in the last {w}h.",
        )
    elif succeeded == 0:
        outcomes = CheckResult(
            "stripe_processing_outcomes",
            "Recent processing outcomes",
            WARNING,
            f"In the last {w}h: 0 successful and {failed_attempts} failed processing attempts.",
            "Open Failed Events and inspect the latest processing attempt.",
        )
    else:
        outcomes = CheckResult(
            "stripe_processing_outcomes",
            "Recent processing outcomes",
            PASS,
            f"In the last {w}h: {succeeded} successful (processed or ignored) and {failed_attempts} failed "
            "processing attempts.",
        )
    checks.append(outcomes)

    retries = m.retries_scheduled_in_window
    checks.append(
        CheckResult(
            "stripe_retry_activity",
            "Retry activity",
            WARNING if retries >= rules.RETRY_ACTIVITY_WARNING else PASS,
            f"{retries} processing retries scheduled in the last {w}h.",
            "Review the attempt timeline of retrying events for a recurring error code."
            if retries >= rules.RETRY_ACTIVITY_WARNING
            else None,
        )
    )
    return checks
