"""Persistence for diagnostic runs and checks."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.diagnostics import DiagnosticCheckORM, DiagnosticRunORM


class DiagnosticRepository:
    def create_run(
        self, session: Session, *, integration_id: UUID, provider: str, started_at: datetime
    ) -> DiagnosticRunORM:
        from app.core.correlation import get_correlation_id

        run = DiagnosticRunORM(
            id=uuid4(),
            integration_id=integration_id,
            provider=provider,
            trigger="manual",
            started_at=started_at,
            overall_status="running",
            correlation_id=get_correlation_id(),
        )
        session.add(run)
        session.flush()
        return run

    def find_running(
        self, session: Session, *, integration_id: UUID, started_after: datetime
    ) -> DiagnosticRunORM | None:
        statement = select(DiagnosticRunORM).where(
            DiagnosticRunORM.integration_id == integration_id,
            DiagnosticRunORM.overall_status == "running",
            DiagnosticRunORM.started_at >= started_after,
        )
        return session.scalars(statement).first()

    def get_run(self, session: Session, run_id: UUID) -> DiagnosticRunORM | None:
        return session.get(DiagnosticRunORM, run_id)

    def list_runs(self, session: Session, *, integration_id: UUID, limit: int) -> list[DiagnosticRunORM]:
        statement = (
            select(DiagnosticRunORM)
            .where(DiagnosticRunORM.integration_id == integration_id)
            .order_by(DiagnosticRunORM.started_at.desc(), DiagnosticRunORM.id.desc())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def checks_for_run(self, session: Session, run_id: UUID) -> list[DiagnosticCheckORM]:
        statement = (
            select(DiagnosticCheckORM)
            .where(DiagnosticCheckORM.diagnostic_run_id == run_id)
            .order_by(DiagnosticCheckORM.position)
        )
        return list(session.scalars(statement).all())

    def status_counts(self, session: Session, run_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
        if not run_ids:
            return {}
        rows = session.execute(
            select(DiagnosticCheckORM.diagnostic_run_id, DiagnosticCheckORM.status, func.count())
            .where(DiagnosticCheckORM.diagnostic_run_id.in_(run_ids))
            .group_by(DiagnosticCheckORM.diagnostic_run_id, DiagnosticCheckORM.status)
        ).all()
        counts: dict[UUID, dict[str, int]] = defaultdict(dict)
        for run_id, status, count in rows:
            counts[run_id][status] = int(count)
        return counts


diagnostic_repository = DiagnosticRepository()
