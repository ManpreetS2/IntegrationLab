"""Shared diagnostic check result type and overall-status precedence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.diagnostics import CheckStatus, DiagnosticRunStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CheckResult:
    check_code: str
    title: str
    status: CheckStatus
    evidence: str
    recommendation: str | None = None
    required: bool = False
    latency_ms: int | None = None
    observed_at: datetime = field(default_factory=_now)


def summarize_checks(checks: list[CheckResult]) -> tuple[DiagnosticRunStatus, str]:
    """Overall status precedence: fail > warning > unknown > pass.

    - fail:    any REQUIRED check failed
    - warning: no required failure, but a warning (or a non-required failure) exists
    - unknown: nothing wrong observed, but a required check lacked evidence
    - pass:    every required check passed (informational checks may be unknown)
    """
    required_failures = [c for c in checks if c.required and c.status == CheckStatus.FAIL]
    if required_failures:
        titles = ", ".join(c.title for c in required_failures)
        return DiagnosticRunStatus.FAIL, f"{len(required_failures)} required check(s) failed: {titles}."

    attention = [
        c
        for c in checks
        if c.status == CheckStatus.WARNING or (c.status == CheckStatus.FAIL and not c.required)
    ]
    if attention:
        titles = ", ".join(c.title for c in attention)
        return (
            DiagnosticRunStatus.WARNING,
            f"No required check failed; {len(attention)} check(s) need attention: {titles}.",
        )

    missing = [c for c in checks if c.required and c.status == CheckStatus.UNKNOWN]
    if missing:
        titles = ", ".join(c.title for c in missing)
        return DiagnosticRunStatus.UNKNOWN, f"Insufficient evidence: {titles} could not be confirmed."

    return DiagnosticRunStatus.PASS, f"All {sum(c.required for c in checks)} required checks passed."
