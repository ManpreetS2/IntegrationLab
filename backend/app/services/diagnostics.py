"""Guided diagnostics: run provider checks and persist the run + checks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.diagnostics import DiagnosticCheckORM, DiagnosticRunORM
from app.db.models.integration import IntegrationORM
from app.models.diagnostics import (
    CheckCounts,
    CheckStatus,
    DiagnosticCheckResponse,
    DiagnosticRunListItem,
    DiagnosticRunResponse,
)
from app.core.correlation import get_correlation_id
from app.repositories.diagnostics import diagnostic_repository
from app.services import reliability_rules as rules
from app.services.audit import audit_service
from app.services.diagnostic_checks import CheckResult, summarize_checks
from app.services.github_diagnostics import run_github_checks
from app.services.stripe_diagnostics import run_stripe_checks

logger = logging.getLogger(__name__)

MAX_RUNS_LIMIT = 50


def _counts(raw: dict[str, int]) -> CheckCounts:
    return CheckCounts(
        passed=raw.get(CheckStatus.PASS.value, 0),
        warning=raw.get(CheckStatus.WARNING.value, 0),
        failed=raw.get(CheckStatus.FAIL.value, 0),
        unknown=raw.get(CheckStatus.UNKNOWN.value, 0),
    )


def _list_item(run: DiagnosticRunORM, counts: dict[str, int]) -> DiagnosticRunListItem:
    return DiagnosticRunListItem(
        id=run.id,
        integration_id=run.integration_id,
        provider=run.provider,
        trigger=run.trigger,
        started_at=run.started_at,
        completed_at=run.completed_at,
        overall_status=run.overall_status,
        summary=run.summary,
        check_counts=_counts(counts),
    )


class DiagnosticsService:
    def run(self, session: Session, integration_id: UUID, *, now: datetime | None = None) -> DiagnosticRunResponse:
        integration = session.get(IntegrationORM, integration_id)
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        if integration.provider not in ("github", "stripe"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Diagnostics are not available for provider '{integration.provider}'.",
            )

        started = now or datetime.now(timezone.utc)
        in_flight = diagnostic_repository.find_running(
            session,
            integration_id=integration_id,
            started_after=started - timedelta(seconds=rules.DIAGNOSTIC_RUN_LOCK_SECONDS),
        )
        if in_flight is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A diagnostic run is already in progress for this integration.",
            )

        run = diagnostic_repository.create_run(
            session, integration_id=integration_id, provider=integration.provider, started_at=started
        )
        # Intentionally commit the in-flight "running" row so concurrent runs can
        # see the lock. Completion + audit are co-committed below.
        session.commit()
        run_id = run.id

        checks = self._execute(session, integration, started)
        overall, summary = summarize_checks(checks)

        run = diagnostic_repository.get_run(session, run_id)
        assert run is not None
        for position, check in enumerate(checks, start=1):
            session.add(
                DiagnosticCheckORM(
                    diagnostic_run_id=run_id,
                    position=position,
                    check_code=check.check_code,
                    title=check.title,
                    status=check.status.value,
                    required=check.required,
                    evidence=check.evidence,
                    recommendation=check.recommendation,
                    latency_ms=check.latency_ms,
                    observed_at=check.observed_at,
                )
            )
        run.overall_status = overall.value
        run.summary = summary
        run.completed_at = max(datetime.now(timezone.utc), started)
        audit_service.record(
            session,
            action="diagnostic_started",
            target_type="diagnostic_run",
            target_id=run_id,
            integration_id=integration_id,
            correlation_id=get_correlation_id(),
            safe_summary=f"Diagnostic run completed with status {overall.value}",
            metadata={
                "diagnostic_run_id": str(run_id),
                "outcome": overall.value,
                "trigger": "manual",
            },
            commit=False,
        )
        session.commit()
        session.expire_all()
        return self.get_run(session, run_id)

    def _execute(self, session: Session, integration: IntegrationORM, now: datetime) -> list[CheckResult]:
        settings = get_settings()
        try:
            if integration.provider == "github":
                return run_github_checks(session, integration, settings=settings)
            return run_stripe_checks(session, integration, settings=settings, now=now)
        except Exception:  # noqa: BLE001 — a diagnostic must always finish with a stored result
            session.rollback()
            logger.exception("Diagnostic check failed for integration %s", integration.id)
            return [
                CheckResult(
                    "diagnostic_execution",
                    "Diagnostic execution",
                    CheckStatus.UNKNOWN,
                    "Diagnostics could not complete because of an internal error.",
                    "Check the API server log for this integration id, then re-run diagnostics.",
                    required=True,
                )
            ]

    def get_run(self, session: Session, run_id: UUID) -> DiagnosticRunResponse:
        run = diagnostic_repository.get_run(session, run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic run not found")
        checks = diagnostic_repository.checks_for_run(session, run_id)
        raw: dict[str, int] = {}
        for check in checks:
            raw[check.status] = raw.get(check.status, 0) + 1
        item = _list_item(run, raw)
        return DiagnosticRunResponse(
            **item.model_dump(),
            checks=[DiagnosticCheckResponse.model_validate(check) for check in checks],
        )

    def list_runs(self, session: Session, integration_id: UUID, *, limit: int) -> list[DiagnosticRunListItem]:
        if session.get(IntegrationORM, integration_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        runs = diagnostic_repository.list_runs(session, integration_id=integration_id, limit=limit)
        counts = diagnostic_repository.status_counts(session, [run.id for run in runs])
        return [_list_item(run, counts.get(run.id, {})) for run in runs]


diagnostics_service = DiagnosticsService()
