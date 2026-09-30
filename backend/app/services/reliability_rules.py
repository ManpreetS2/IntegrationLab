"""Single home for reliability thresholds, severities, and safe failure wording.

These are local IntegrationLab dashboard thresholds — NOT provider guarantees
or SLAs. Tune them here; nothing else should hard-code them.
"""

from __future__ import annotations

from app.models.reliability import LatencyBand, Severity

# Evidence window (hours) for "recent" reliability evidence.
DEFAULT_WINDOW_HOURS = 24
MIN_WINDOW_HOURS = 1
MAX_WINDOW_HOURS = 168

# Latency bands for a single real provider request.
LATENCY_ELEVATED_MS = 500
LATENCY_SLOW_MS = 1500

# Error rate is only treated as meaningful with enough samples.
MIN_SAMPLE_FOR_ERROR_RATE = 4
ERROR_RATE_DEGRADED = 0.25
REPEATED_FAILURES_DEGRADED = 3

# GitHub quota: below this, remaining requests count as "low".
RATE_LIMIT_LOW_REMAINING = 100

# Stripe webhook processing.
STALE_PROCESSING_MINUTES = 5  # matches StripeWebhookProcessor.stale_after
STALE_PENDING_MINUTES = 15
RETRY_ACTIVITY_WARNING = 5

# Diagnostics: an unfinished run blocks a new one for this long.
DIAGNOSTIC_RUN_LOCK_SECONDS = 120


def latency_band(latency_ms: int | None) -> LatencyBand | None:
    if latency_ms is None:
        return None
    if latency_ms > LATENCY_SLOW_MS:
        return LatencyBand.SLOW
    if latency_ms >= LATENCY_ELEVATED_MS:
        return LatencyBand.ELEVATED
    return LatencyBand.NORMAL


_GITHUB_ERROR_SUMMARIES = {
    "github_timeout": "GitHub request timed out.",
    "github_transport_error": "GitHub request failed before a response was received.",
    "github_unauthorized": "GitHub rejected the stored credential (HTTP 401).",
    "github_forbidden": "GitHub denied access to the requested resource (HTTP 403).",
    "github_rate_limited": "GitHub rate limit was reached.",
    "github_not_found": "GitHub returned HTTP 404 for the requested resource.",
    "github_server_error": "GitHub returned a server error (5xx).",
    "github_malformed_json": "GitHub returned a response that was not valid JSON.",
    "github_oauth_error": "GitHub OAuth token endpoint returned an error.",
    "github_client_error": "GitHub rejected the request (4xx).",
}


def provider_failure_code(error_code: str | None, status_code: int | None) -> str:
    if error_code:
        return error_code
    if status_code is None:
        return "provider_no_response"
    return f"http_{status_code}"


def provider_failure_summary(provider: str, code: str, status_code: int | None) -> str:
    if code in _GITHUB_ERROR_SUMMARIES:
        return _GITHUB_ERROR_SUMMARIES[code]
    label = provider.capitalize()
    if status_code is not None:
        return f"{label} request failed with HTTP {status_code}."
    return f"{label} request failed without an HTTP response."


def provider_failure_severity(code: str, status_code: int | None) -> Severity:
    if code == "github_rate_limited" or status_code == 429:
        return Severity.WARNING
    if code == "github_not_found" or status_code == 404:
        return Severity.WARNING
    return Severity.ERROR


WEBHOOK_FAILED_SEVERITY = Severity.ERROR
WEBHOOK_RETRY_SEVERITY = Severity.WARNING
SIMULATION_SEVERITY = Severity.INFO
DIAGNOSTIC_FAIL_SEVERITY = Severity.ERROR
DATABASE_UNAVAILABLE_SEVERITY = Severity.CRITICAL

_WEBHOOK_ERROR_SUMMARIES = {
    "webhook_invalid_event_data": "Webhook event is missing data required by its handler.",
    "webhook_handler_temporary_failure": "Webhook handler hit a temporary failure.",
    "webhook_processing_error": "Unexpected error while processing a webhook event.",
    "webhook_processing_abandoned": "Webhook processing did not finish (worker stopped).",
}


def webhook_failure_summary(code: str | None, status: str, event_type: str) -> str:
    base = _WEBHOOK_ERROR_SUMMARIES.get(code or "", "Webhook processing failed.")
    if status == "retry_scheduled":
        return f"{event_type}: {base} Retry scheduled."
    return f"{event_type}: {base} Moved to failed queue."
