"""Repositories for support cases, notes, evidence, history, and audit listing."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.support import (
    OperatorAuditEventORM,
    SupportCaseEvidenceORM,
    SupportCaseHistoryORM,
    SupportCaseNoteORM,
    SupportCaseORM,
)


class SupportCaseRepository:
    def get(self, session: Session, case_id: UUID) -> SupportCaseORM | None:
        return session.get(SupportCaseORM, case_id)

    def list(
        self,
        session: Session,
        *,
        status: str | None = None,
        severity: str | None = None,
        integration_id: UUID | None = None,
        environment: str | None = None,
        open_only: bool | None = None,
    ) -> list[SupportCaseORM]:
        statement = select(SupportCaseORM)
        if status:
            statement = statement.where(SupportCaseORM.status == status)
        if severity:
            statement = statement.where(SupportCaseORM.severity == severity)
        if integration_id:
            statement = statement.where(SupportCaseORM.integration_id == integration_id)
        if environment:
            statement = statement.where(SupportCaseORM.environment == environment)
        if open_only is True:
            statement = statement.where(SupportCaseORM.status != "resolved")
        if open_only is False:
            statement = statement.where(SupportCaseORM.status == "resolved")
        statement = statement.order_by(SupportCaseORM.opened_at.desc())
        return list(session.scalars(statement).all())

    def next_case_number(self, session: Session) -> str:
        """Allocate the next human-readable case number via a DB sequence.

        Gaps are allowed. Uniqueness is guaranteed by ``nextval`` + the
        ``uq_support_cases_case_number`` constraint — not by counting rows.
        """
        next_val = session.execute(text("SELECT nextval('support_case_number_seq')")).scalar()
        if next_val is None:
            raise RuntimeError("support_case_number_seq returned no value")
        return f"CASE-{int(next_val):05d}"

    def add(self, session: Session, case: SupportCaseORM) -> SupportCaseORM:
        session.add(case)
        session.flush()
        return case

    def list_notes(self, session: Session, case_id: UUID) -> list[SupportCaseNoteORM]:
        statement = (
            select(SupportCaseNoteORM)
            .where(SupportCaseNoteORM.support_case_id == case_id)
            .order_by(SupportCaseNoteORM.created_at.asc())
        )
        return list(session.scalars(statement).all())

    def list_evidence(self, session: Session, case_id: UUID) -> list[SupportCaseEvidenceORM]:
        statement = (
            select(SupportCaseEvidenceORM)
            .where(SupportCaseEvidenceORM.support_case_id == case_id)
            .order_by(SupportCaseEvidenceORM.pinned_at.desc())
        )
        return list(session.scalars(statement).all())

    def list_history(self, session: Session, case_id: UUID) -> list[SupportCaseHistoryORM]:
        statement = (
            select(SupportCaseHistoryORM)
            .where(SupportCaseHistoryORM.support_case_id == case_id)
            .order_by(SupportCaseHistoryORM.created_at.asc())
        )
        return list(session.scalars(statement).all())

    def get_evidence(
        self, session: Session, evidence_row_id: UUID
    ) -> SupportCaseEvidenceORM | None:
        return session.get(SupportCaseEvidenceORM, evidence_row_id)

    def find_evidence_ref(
        self,
        session: Session,
        case_id: UUID,
        evidence_type: str,
        evidence_id: UUID,
    ) -> SupportCaseEvidenceORM | None:
        statement = select(SupportCaseEvidenceORM).where(
            SupportCaseEvidenceORM.support_case_id == case_id,
            SupportCaseEvidenceORM.evidence_type == evidence_type,
            SupportCaseEvidenceORM.evidence_id == evidence_id,
        )
        return session.scalars(statement).first()


class AuditEventRepository:
    def list(
        self,
        session: Session,
        *,
        action: str | None = None,
        integration_id: UUID | None = None,
        support_case_id: UUID | None = None,
        target_type: str | None = None,
        outcome: str | None = None,
        correlation_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[OperatorAuditEventORM]:
        statement = select(OperatorAuditEventORM)
        if action:
            statement = statement.where(OperatorAuditEventORM.action == action)
        if integration_id:
            statement = statement.where(OperatorAuditEventORM.integration_id == integration_id)
        if support_case_id:
            statement = statement.where(OperatorAuditEventORM.support_case_id == support_case_id)
        if target_type:
            statement = statement.where(OperatorAuditEventORM.target_type == target_type)
        if outcome:
            statement = statement.where(OperatorAuditEventORM.outcome == outcome)
        if correlation_id:
            statement = statement.where(OperatorAuditEventORM.correlation_id == correlation_id)
        if since:
            statement = statement.where(OperatorAuditEventORM.created_at >= since)
        if until:
            statement = statement.where(OperatorAuditEventORM.created_at <= until)
        statement = statement.order_by(OperatorAuditEventORM.created_at.desc()).limit(
            min(max(limit, 1), 500)
        )
        return list(session.scalars(statement).all())


support_case_repository = SupportCaseRepository()
audit_event_repository = AuditEventRepository()
