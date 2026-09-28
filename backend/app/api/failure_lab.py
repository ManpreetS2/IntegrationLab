"""Failure Lab API — sandboxed provider failure reproduction."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.failure_lab import (
    FailureLabRunListItem,
    FailureLabRunRequest,
    FailureLabRunResponse,
    FailureScenario,
    FailureScenarioInfo,
)
from app.services.failure_lab import failure_lab_service

router = APIRouter(prefix="/api/failure-lab", tags=["failure-lab"])


@router.get("/scenarios", response_model=list[FailureScenarioInfo])
def list_failure_scenarios() -> list[FailureScenarioInfo]:
    """Return available Failure Lab scenarios (server-defined only)."""
    return failure_lab_service.list_scenarios()


@router.post("/run", response_model=FailureLabRunResponse)
def run_failure_scenario(
    payload: FailureLabRunRequest,
    db: Session = Depends(get_db),
) -> FailureLabRunResponse:
    """Run a sandboxed failure simulation (does not call GitHub or mutate credentials)."""
    return failure_lab_service.run(db, payload)


@router.get("/runs", response_model=list[FailureLabRunListItem])
def list_failure_runs(
    integration_id: UUID | None = Query(default=None),
    scenario: FailureScenario | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[FailureLabRunListItem]:
    """List recent Failure Lab runs (newest first)."""
    return failure_lab_service.list_runs(
        db,
        integration_id=integration_id,
        scenario=scenario,
        limit=limit,
    )


@router.get("/runs/{run_id}", response_model=FailureLabRunResponse)
def get_failure_run(
    run_id: UUID,
    db: Session = Depends(get_db),
) -> FailureLabRunResponse:
    """Return one Failure Lab run with full diagnosis details."""
    return failure_lab_service.get_run(db, run_id)
