"""Support case lifecycle, evidence pinning, notes, and derived timeline."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.correlation import get_correlation_id, require_correlation_id, short_correlation_id
from app.db.models.diagnostics import DiagnosticRunORM
from app.db.models.failure_lab import FailureLabRunORM
from app.db.models.oauth import ProviderRequestLogORM
from app.db.models.support import (
    OperatorAuditEventORM,
    SupportCaseEvidenceORM,
    SupportCaseHistoryORM,
    SupportCaseNoteORM,
    SupportCaseORM,
)
from app.db.models.webhook import WebhookEventORM, WebhookProcessingAttemptORM
from app.models.support import (
    CaseSeverity,
    CaseStatus,
    EvidenceType,
    SupportCaseCreate,
    SupportCaseEvidenceCreate,
    SupportCaseNoteCreate,
    SupportCaseUpdate,
    TimelineItem,
)
from app.repositories.integrations import integration_repository
from app.repositories.support import support_case_repository
from app.services.audit import audit_service

# Valid directed transitions. REOPENED behaves like INVESTIGATING for forward progress.
_ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.INVESTIGATING: {CaseStatus.IDENTIFIED, CaseStatus.MONITORING, CaseStatus.RESOLVED},
    CaseStatus.IDENTIFIED: {CaseStatus.MONITORING, CaseStatus.RESOLVED, CaseStatus.INVESTIGATING},
    CaseStatus.MONITORING: {CaseStatus.RESOLVED, CaseStatus.IDENTIFIED, CaseStatus.INVESTIGATING},
    CaseStatus.RESOLVED: {CaseStatus.REOPENED},
    CaseStatus.REOPENED: {CaseStatus.IDENTIFIED, CaseStatus.MONITORING, CaseStatus.RESOLVED},
}


class SupportCaseService:
    def create_case(self, session: Session, payload: SupportCaseCreate) -> SupportCaseORM:
        integration = integration_repository.get_by_id(session, payload.integration_id)
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

        correlation_id = require_correlation_id()
        now = datetime.now(timezone.utc)
        environment = (
            payload.environment.value
            if payload.environment is not None
            else (integration.environment or "local")
        )

        # Phase 1 cases are operator-created/manual → acknowledged at open.
        case = SupportCaseORM(
            id=uuid4(),
            case_number=support_case_repository.next_case_number(session),
            integration_id=integration.id,
            environment=environment,
            title=payload.title,
            severity=payload.severity.value,
            status=CaseStatus.INVESTIGATING.value,
            owner=payload.owner or "operator",
            impact_summary=payload.impact_summary,
            suspected_cause=payload.suspected_cause,
            correlation_id=correlation_id,
            opened_at=now,
            acknowledged_at=now,
            created_at=now,
            updated_at=now,
        )
        support_case_repository.add(session, case)
        self._add_history(
            session,
            case,
            event_type="case_opened",
            summary=f"Support case {case.case_number} opened",
            to_value=case.status,
        )

        if payload.source_evidence_type is not None and payload.source_evidence_id is not None:
            self.pin_evidence(
                session,
                case.id,
                SupportCaseEvidenceCreate(
                    evidence_type=payload.source_evidence_type,
                    evidence_id=payload.source_evidence_id,
                ),
                commit=False,
            )

        audit_service.record(
            session,
            action="support_case_created",
            target_type="support_case",
            target_id=case.id,
            integration_id=case.integration_id,
            support_case_id=case.id,
            correlation_id=correlation_id,
            safe_summary=f"Opened {case.case_number}",
            metadata={
                "case_number": case.case_number,
                "severity": case.severity,
                "environment": case.environment,
                "status": case.status,
            },
        )
        session.commit()
        session.refresh(case)
        return case

    def update_case(
        self, session: Session, case_id: UUID, payload: SupportCaseUpdate
    ) -> SupportCaseORM:
        case = self._require_case(session, case_id)
        correlation_id = require_correlation_id()
        data = payload.model_dump(exclude_unset=True)

        if "status" in data and data["status"] is not None:
            status_value = data.pop("status")
            new_status = (
                status_value
                if isinstance(status_value, CaseStatus)
                else CaseStatus(status_value)
            )
            self._transition_status(session, case, new_status)

        if "severity" in data and data["severity"] is not None:
            severity_value = data.pop("severity")
            new_severity = (
                severity_value.value
                if isinstance(severity_value, CaseSeverity)
                else str(severity_value)
            )
            if new_severity != case.severity:
                old = case.severity
                case.severity = new_severity
                self._add_history(
                    session,
                    case,
                    event_type="severity_changed",
                    summary=f"Severity changed from {old} to {new_severity}",
                    from_value=old,
                    to_value=new_severity,
                )
                audit_service.record(
                    session,
                    action="support_case_severity_changed",
                    target_type="support_case",
                    target_id=case.id,
                    integration_id=case.integration_id,
                    support_case_id=case.id,
                    correlation_id=correlation_id,
                    safe_summary=f"{case.case_number} severity {old} → {new_severity}",
                    metadata={
                        "case_number": case.case_number,
                        "from_severity": old,
                        "to_severity": new_severity,
                    },
                )

        for field in (
            "title",
            "owner",
            "impact_summary",
            "suspected_cause",
            "confirmed_root_cause",
            "mitigation_summary",
            "resolution_summary",
        ):
            if field in data:
                setattr(case, field, data[field])

        case.updated_at = datetime.now(timezone.utc)
        session.add(case)
        session.commit()
        session.refresh(case)
        return case

    def add_note(
        self, session: Session, case_id: UUID, payload: SupportCaseNoteCreate
    ) -> SupportCaseNoteORM:
        case = self._require_case(session, case_id)
        correlation_id = require_correlation_id()
        note = SupportCaseNoteORM(
            id=uuid4(),
            support_case_id=case.id,
            body=payload.body,
            correlation_id=correlation_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(note)
        case.updated_at = datetime.now(timezone.utc)
        audit_service.record(
            session,
            action="support_case_note_added",
            target_type="support_case_note",
            target_id=note.id,
            integration_id=case.integration_id,
            support_case_id=case.id,
            correlation_id=correlation_id,
            safe_summary=f"Note added on {case.case_number}",
            metadata={"case_number": case.case_number, "note_id": str(note.id)},
        )
        session.commit()
        session.refresh(note)
        return note

    def pin_evidence(
        self,
        session: Session,
        case_id: UUID,
        payload: SupportCaseEvidenceCreate,
        *,
        commit: bool = True,
    ) -> SupportCaseEvidenceORM:
        case = self._require_case(session, case_id)
        existing = support_case_repository.find_evidence_ref(
            session, case.id, payload.evidence_type.value, payload.evidence_id
        )
        if existing is not None:
            return existing

        resolved = self._resolve_evidence(
            session,
            case,
            payload.evidence_type,
            payload.evidence_id,
        )
        correlation_id = resolved.get("correlation_id") or require_correlation_id()
        label = payload.safe_label or resolved["safe_label"]
        row = SupportCaseEvidenceORM(
            id=uuid4(),
            support_case_id=case.id,
            evidence_type=payload.evidence_type.value,
            evidence_id=payload.evidence_id,
            safe_label=label[:255],
            is_simulated=bool(resolved["is_simulated"]),
            correlation_id=correlation_id,
            pinned_at=datetime.now(timezone.utc),
        )
        session.add(row)
        case.updated_at = datetime.now(timezone.utc)
        self._add_history(
            session,
            case,
            event_type="evidence_pinned",
            summary=f"Pinned {payload.evidence_type.value}",
            to_value=str(payload.evidence_id),
        )
        audit_service.record(
            session,
            action="evidence_pinned",
            target_type="support_case_evidence",
            target_id=row.id,
            integration_id=case.integration_id,
            support_case_id=case.id,
            correlation_id=correlation_id,
            safe_summary=f"Pinned evidence on {case.case_number}",
            metadata={
                "case_number": case.case_number,
                "evidence_type": payload.evidence_type.value,
                "evidence_id": str(payload.evidence_id),
                "is_simulated": row.is_simulated,
            },
        )
        if commit:
            session.commit()
            session.refresh(row)
        else:
            session.flush()
        return row

    def unpin_evidence(self, session: Session, case_id: UUID, evidence_row_id: UUID) -> None:
        case = self._require_case(session, case_id)
        row = support_case_repository.get_evidence(session, evidence_row_id)
        if row is None or row.support_case_id != case.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence pin not found")
        correlation_id = require_correlation_id()
        evidence_type = row.evidence_type
        evidence_id = row.evidence_id
        session.delete(row)
        case.updated_at = datetime.now(timezone.utc)
        self._add_history(
            session,
            case,
            event_type="evidence_unpinned",
            summary=f"Unpinned {evidence_type}",
            from_value=str(evidence_id),
        )
        audit_service.record(
            session,
            action="evidence_unpinned",
            target_type="support_case_evidence",
            target_id=evidence_row_id,
            integration_id=case.integration_id,
            support_case_id=case.id,
            correlation_id=correlation_id,
            safe_summary=f"Unpinned evidence on {case.case_number}",
            metadata={
                "case_number": case.case_number,
                "evidence_type": evidence_type,
                "evidence_id": str(evidence_id),
            },
        )
        session.commit()

    def build_timeline(self, session: Session, case_id: UUID) -> list[TimelineItem]:
        """Derive a chronological timeline.

        Operator actions (open/status/severity/pin/unpin/notes) use their own
        timestamps. Linked evidence uses ``occurred_at`` as the sort key so a
        late pin does not imply the underlying event happened at pin time.
        """
        case = self._require_case(session, case_id)
        items: list[TimelineItem] = []

        for event in support_case_repository.list_history(session, case.id):
            items.append(
                TimelineItem(
                    timestamp=event.created_at,
                    type=event.event_type,
                    title=event.event_type.replace("_", " ").title(),
                    summary=event.summary,
                    source_type="case_history",
                    source_id=event.id,
                    correlation_id=event.correlation_id,
                    correlation_short=short_correlation_id(event.correlation_id),
                )
            )

        for note in support_case_repository.list_notes(session, case.id):
            items.append(
                TimelineItem(
                    timestamp=note.created_at,
                    type="note",
                    title="Operator note",
                    summary=note.body,
                    source_type="support_case_note",
                    source_id=note.id,
                    correlation_id=note.correlation_id,
                    correlation_short=short_correlation_id(note.correlation_id),
                )
            )

        for pin in support_case_repository.list_evidence(session, case.id):
            occurred_at = self._evidence_occurred_at(
                session, EvidenceType(pin.evidence_type), pin.evidence_id
            )
            sort_at = occurred_at or pin.pinned_at
            prefix = "[SIMULATED] " if pin.is_simulated else ""
            items.append(
                TimelineItem(
                    timestamp=sort_at,
                    type=pin.evidence_type,
                    title=f"{prefix}Linked evidence",
                    summary=pin.safe_label,
                    source_type=pin.evidence_type,
                    source_id=pin.evidence_id,
                    correlation_id=pin.correlation_id,
                    correlation_short=short_correlation_id(pin.correlation_id),
                    is_simulated=pin.is_simulated,
                    occurred_at=occurred_at,
                    pinned_at=pin.pinned_at,
                )
            )

        items.sort(key=lambda item: (item.timestamp, item.type, str(item.source_id or "")))
        return items

    def _transition_status(
        self, session: Session, case: SupportCaseORM, new_status: CaseStatus
    ) -> None:
        current = CaseStatus(case.status)
        if new_status == current:
            return
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition: {current.value} → {new_status.value}",
            )

        now = datetime.now(timezone.utc)
        old = case.status
        case.status = new_status.value
        if new_status == CaseStatus.IDENTIFIED:
            case.identified_at = now
        elif new_status == CaseStatus.MONITORING:
            case.monitoring_at = now
        elif new_status == CaseStatus.RESOLVED:
            case.resolved_at = now
        elif new_status == CaseStatus.REOPENED:
            case.reopened_at = now
            case.resolved_at = None

        correlation_id = require_correlation_id()
        self._add_history(
            session,
            case,
            event_type="status_changed",
            summary=f"Status changed from {old} to {new_status.value}",
            from_value=old,
            to_value=new_status.value,
        )
        audit_service.record(
            session,
            action="support_case_status_changed",
            target_type="support_case",
            target_id=case.id,
            integration_id=case.integration_id,
            support_case_id=case.id,
            correlation_id=correlation_id,
            safe_summary=f"{case.case_number} status {old} → {new_status.value}",
            metadata={
                "case_number": case.case_number,
                "from_status": old,
                "to_status": new_status.value,
            },
        )

    def _add_history(
        self,
        session: Session,
        case: SupportCaseORM,
        *,
        event_type: str,
        summary: str,
        from_value: str | None = None,
        to_value: str | None = None,
    ) -> SupportCaseHistoryORM:
        row = SupportCaseHistoryORM(
            id=uuid4(),
            support_case_id=case.id,
            event_type=event_type,
            from_value=from_value,
            to_value=to_value,
            summary=summary,
            correlation_id=get_correlation_id(),
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
        return row

    def _require_case(self, session: Session, case_id: UUID) -> SupportCaseORM:
        case = support_case_repository.get(session, case_id)
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support case not found")
        return case

    def _resolve_evidence(
        self,
        session: Session,
        case: SupportCaseORM,
        evidence_type: EvidenceType,
        evidence_id: UUID,
    ) -> dict:
        integration_id = case.integration_id

        if evidence_type == EvidenceType.PROVIDER_REQUEST:
            row = session.get(ProviderRequestLogORM, evidence_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Provider request not found")
            # Must be scoped to the same integration — unscoped rows are not attachable.
            if row.integration_id is None or row.integration_id != integration_id:
                raise HTTPException(
                    status_code=400,
                    detail="Provider request evidence must belong to the case integration",
                )
            return {
                "safe_label": f"{row.provider} {row.method} {row.endpoint} ({row.status_code})",
                "is_simulated": row.is_simulated,
                "correlation_id": row.correlation_id,
                "occurred_at": row.timestamp,
            }

        if evidence_type == EvidenceType.WEBHOOK_EVENT:
            row = session.get(WebhookEventORM, evidence_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Webhook event not found")
            if row.integration_id != integration_id:
                raise HTTPException(status_code=400, detail="Evidence belongs to another integration")
            return {
                "safe_label": f"{row.provider} {row.event_type} [{row.processing_status}]",
                "is_simulated": False,
                "correlation_id": None,
                "occurred_at": row.first_received_at,
            }

        if evidence_type == EvidenceType.WEBHOOK_ATTEMPT:
            row = session.get(WebhookProcessingAttemptORM, evidence_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Webhook attempt not found")
            event = session.get(WebhookEventORM, row.webhook_event_id)
            if event is None or event.integration_id != integration_id:
                raise HTTPException(status_code=400, detail="Evidence belongs to another integration")
            return {
                "safe_label": f"Attempt #{row.attempt_number} → {row.outcome}",
                "is_simulated": False,
                "correlation_id": row.correlation_id,
                "occurred_at": row.started_at,
            }

        if evidence_type == EvidenceType.DIAGNOSTIC_RUN:
            row = session.get(DiagnosticRunORM, evidence_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Diagnostic run not found")
            if row.integration_id != integration_id:
                raise HTTPException(status_code=400, detail="Evidence belongs to another integration")
            return {
                "safe_label": f"Diagnostic {row.overall_status}: {row.summary or row.provider}",
                "is_simulated": False,
                "correlation_id": row.correlation_id,
                "occurred_at": row.started_at,
            }

        if evidence_type == EvidenceType.FAILURE_LAB_RUN:
            row = session.get(FailureLabRunORM, evidence_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Failure Lab run not found")
            if row.integration_id != integration_id:
                raise HTTPException(status_code=400, detail="Evidence belongs to another integration")
            return {
                "safe_label": f"[SIMULATED] {row.scenario}: {row.diagnosis_title}",
                "is_simulated": True,
                "correlation_id": row.correlation_id,
                "occurred_at": row.created_at,
            }

        if evidence_type == EvidenceType.AUDIT_EVENT:
            row = session.get(OperatorAuditEventORM, evidence_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Audit event not found")
            if row.integration_id is not None:
                if row.integration_id != integration_id:
                    raise HTTPException(
                        status_code=400, detail="Evidence belongs to another integration"
                    )
            elif row.support_case_id != case.id:
                # Unscoped audit rows may only attach when already about this case.
                raise HTTPException(
                    status_code=400,
                    detail="Unscoped audit evidence can only be pinned to its related support case",
                )
            return {
                "safe_label": f"Audit: {row.action}",
                "is_simulated": False,
                "correlation_id": row.correlation_id,
                "occurred_at": row.created_at,
            }

        raise HTTPException(status_code=400, detail="Unsupported evidence type")

    def _evidence_occurred_at(
        self,
        session: Session,
        evidence_type: EvidenceType,
        evidence_id: UUID,
    ) -> datetime | None:
        try:
            if evidence_type == EvidenceType.PROVIDER_REQUEST:
                row = session.get(ProviderRequestLogORM, evidence_id)
                return row.timestamp if row else None
            if evidence_type == EvidenceType.WEBHOOK_EVENT:
                row = session.get(WebhookEventORM, evidence_id)
                return row.first_received_at if row else None
            if evidence_type == EvidenceType.WEBHOOK_ATTEMPT:
                row = session.get(WebhookProcessingAttemptORM, evidence_id)
                return row.started_at if row else None
            if evidence_type == EvidenceType.DIAGNOSTIC_RUN:
                row = session.get(DiagnosticRunORM, evidence_id)
                return row.started_at if row else None
            if evidence_type == EvidenceType.FAILURE_LAB_RUN:
                row = session.get(FailureLabRunORM, evidence_id)
                return row.created_at if row else None
            if evidence_type == EvidenceType.AUDIT_EVENT:
                row = session.get(OperatorAuditEventORM, evidence_id)
                return row.created_at if row else None
        except Exception:  # noqa: BLE001 — timeline must still render
            return None
        return None


support_case_service = SupportCaseService()
