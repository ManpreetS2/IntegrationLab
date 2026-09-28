"""Repository for Failure Lab runs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.failure_lab import FailureLabRunORM


class FailureLabRunRepository:
    def create(
        self,
        session: Session,
        *,
        integration_id: UUID,
        provider: str,
        scenario: str,
        method: str,
        endpoint: str,
        status_code: int | None,
        latency_ms: int,
        error_code: str | None,
        diagnosis_code: str,
        diagnosis_title: str,
        diagnosis_summary: str,
        retryable: bool,
        evidence_summary: str | None,
        recommended_checks: str | None,
        rate_limit_remaining: int | None,
    ) -> FailureLabRunORM:
        row = FailureLabRunORM(
            id=uuid4(),
            integration_id=integration_id,
            provider=provider,
            scenario=scenario,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=latency_ms,
            error_code=error_code,
            diagnosis_code=diagnosis_code,
            diagnosis_title=diagnosis_title,
            diagnosis_summary=diagnosis_summary,
            retryable=retryable,
            evidence_summary=evidence_summary,
            recommended_checks=recommended_checks,
            rate_limit_remaining=rate_limit_remaining,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
        return row

    def list_recent(
        self,
        session: Session,
        *,
        integration_id: UUID | None = None,
        scenario: str | None = None,
        limit: int = 25,
    ) -> list[FailureLabRunORM]:
        statement = select(FailureLabRunORM).order_by(FailureLabRunORM.created_at.desc())
        if integration_id is not None:
            statement = statement.where(FailureLabRunORM.integration_id == integration_id)
        if scenario:
            statement = statement.where(FailureLabRunORM.scenario == scenario)
        statement = statement.limit(limit)
        return list(session.scalars(statement).all())

    def get_by_id(self, session: Session, run_id: UUID) -> FailureLabRunORM | None:
        return session.get(FailureLabRunORM, run_id)


failure_lab_run_repository = FailureLabRunRepository()
