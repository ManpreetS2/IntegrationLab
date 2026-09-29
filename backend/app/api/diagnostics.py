"""Guided diagnostics API (manual, operator-triggered)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.diagnostics import DiagnosticRunListItem, DiagnosticRunResponse
from app.services.diagnostics import MAX_RUNS_LIMIT, diagnostics_service

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("/runs/{run_id}", response_model=DiagnosticRunResponse)
def get_diagnostic_run(run_id: UUID, db: Session = Depends(get_db)) -> DiagnosticRunResponse:
    return diagnostics_service.get_run(db, run_id)


@router.post("/{integration_id}/run", response_model=DiagnosticRunResponse)
def run_diagnostics(integration_id: UUID, db: Session = Depends(get_db)) -> DiagnosticRunResponse:
    return diagnostics_service.run(db, integration_id)


@router.get("/{integration_id}/runs", response_model=list[DiagnosticRunListItem])
def list_diagnostic_runs(
    integration_id: UUID,
    limit: int = Query(default=20, ge=1, le=MAX_RUNS_LIMIT),
    db: Session = Depends(get_db),
) -> list[DiagnosticRunListItem]:
    return diagnostics_service.list_runs(db, integration_id, limit=limit)
