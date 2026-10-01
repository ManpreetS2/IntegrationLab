"""HTTP routes for support cases, notes, evidence, and timeline."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.correlation import correlation_scope, parse_correlation_id
from app.core.database import get_db
from app.models.support import (
    CaseSeverity,
    CaseStatus,
    Environment,
    SupportCase,
    SupportCaseCreate,
    SupportCaseDetail,
    SupportCaseEvidence,
    SupportCaseEvidenceCreate,
    SupportCaseNote,
    SupportCaseNoteCreate,
    SupportCaseUpdate,
    TimelineItem,
)
from app.repositories.support import support_case_repository
from app.services.support_cases import support_case_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/support-cases", tags=["support-cases"])


def _correlation_dep(
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID"),
):
    return parse_correlation_id(x_correlation_id)


@router.get("", response_model=list[SupportCase])
def list_support_cases(
    status_filter: Optional[CaseStatus] = Query(default=None, alias="status"),
    severity: Optional[CaseSeverity] = None,
    integration_id: Optional[UUID] = None,
    environment: Optional[Environment] = None,
    open_only: Optional[bool] = None,
    db: Session = Depends(get_db),
) -> list[SupportCase]:
    try:
        rows = support_case_repository.list(
            db,
            status=status_filter.value if status_filter else None,
            severity=severity.value if severity else None,
            integration_id=integration_id,
            environment=environment.value if environment else None,
            open_only=open_only,
        )
        return [SupportCase.model_validate(row) for row in rows]
    except SQLAlchemyError:
        logger.exception("Failed to list support cases")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.post("", response_model=SupportCaseDetail, status_code=status.HTTP_201_CREATED)
def create_support_case(
    payload: SupportCaseCreate,
    db: Session = Depends(get_db),
    correlation_id: Optional[UUID] = Depends(_correlation_dep),
) -> SupportCaseDetail:
    try:
        with correlation_scope(correlation_id):
            case = support_case_service.create_case(db, payload)
        return _detail(db, case.id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to create support case")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.get("/{case_id}", response_model=SupportCaseDetail)
def get_support_case(case_id: UUID, db: Session = Depends(get_db)) -> SupportCaseDetail:
    try:
        return _detail(db, case_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Failed to load support case")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.patch("/{case_id}", response_model=SupportCaseDetail)
def patch_support_case(
    case_id: UUID,
    payload: SupportCaseUpdate,
    db: Session = Depends(get_db),
    correlation_id: Optional[UUID] = Depends(_correlation_dep),
) -> SupportCaseDetail:
    try:
        with correlation_scope(correlation_id):
            support_case_service.update_case(db, case_id, payload)
        return _detail(db, case_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to update support case")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.get("/{case_id}/timeline", response_model=list[TimelineItem])
def get_timeline(case_id: UUID, db: Session = Depends(get_db)) -> list[TimelineItem]:
    try:
        return support_case_service.build_timeline(db, case_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Failed to build timeline")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.post(
    "/{case_id}/notes",
    response_model=SupportCaseNote,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    case_id: UUID,
    payload: SupportCaseNoteCreate,
    db: Session = Depends(get_db),
    correlation_id: Optional[UUID] = Depends(_correlation_dep),
) -> SupportCaseNote:
    try:
        with correlation_scope(correlation_id):
            note = support_case_service.add_note(db, case_id, payload)
        return SupportCaseNote.model_validate(note)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to add note")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.post(
    "/{case_id}/evidence",
    response_model=SupportCaseEvidence,
    status_code=status.HTTP_201_CREATED,
)
def pin_evidence(
    case_id: UUID,
    payload: SupportCaseEvidenceCreate,
    db: Session = Depends(get_db),
    correlation_id: Optional[UUID] = Depends(_correlation_dep),
) -> SupportCaseEvidence:
    try:
        with correlation_scope(correlation_id):
            row = support_case_service.pin_evidence(db, case_id, payload)
        return SupportCaseEvidence.model_validate(row)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to pin evidence")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


@router.delete(
    "/{case_id}/evidence/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unpin_evidence(
    case_id: UUID,
    evidence_id: UUID,
    db: Session = Depends(get_db),
    correlation_id: Optional[UUID] = Depends(_correlation_dep),
) -> None:
    try:
        with correlation_scope(correlation_id):
            support_case_service.unpin_evidence(db, case_id, evidence_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to unpin evidence")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        ) from None


def _detail(db: Session, case_id: UUID) -> SupportCaseDetail:
    case = support_case_repository.get(db, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support case not found")
    notes = support_case_repository.list_notes(db, case_id)
    evidence = support_case_repository.list_evidence(db, case_id)
    base = SupportCase.model_validate(case)
    return SupportCaseDetail(
        **base.model_dump(),
        notes=[SupportCaseNote.model_validate(n) for n in notes],
        evidence=[SupportCaseEvidence.model_validate(e) for e in evidence],
    )
