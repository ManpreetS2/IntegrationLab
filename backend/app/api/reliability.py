"""Reliability read APIs (passive: no provider calls on page load)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integration import IntegrationProvider
from app.models.reliability import (
    FailureItem,
    FailureSource,
    HealthState,
    IntegrationReliabilityDetail,
    ReliabilityOverview,
    RequestMetricsResponse,
    SystemHealth,
)
from app.services import reliability_rules as rules
from app.services.reliability import (
    DatabaseUnavailableError,
    database_unavailable,
    reliability_service,
)

router = APIRouter(prefix="/api/reliability", tags=["reliability"])

WindowHours = Query(
    default=rules.DEFAULT_WINDOW_HOURS, ge=rules.MIN_WINDOW_HOURS, le=rules.MAX_WINDOW_HOURS
)


@router.get("/system", response_model=SystemHealth)
def system_health(response: Response, db: Session = Depends(get_db)) -> SystemHealth:
    """Database readiness only; other infrastructure does not exist yet."""
    result = reliability_service.system(db)
    if result.database == HealthState.FAILED:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get("/overview", response_model=ReliabilityOverview)
def reliability_overview(
    window_hours: int = WindowHours,
    db: Session = Depends(get_db),
) -> ReliabilityOverview:
    try:
        return reliability_service.overview(db, window_hours=window_hours)
    except DatabaseUnavailableError:
        raise database_unavailable() from None


@router.get("/integrations/{integration_id}", response_model=IntegrationReliabilityDetail)
def integration_reliability(
    integration_id: UUID,
    window_hours: int = WindowHours,
    db: Session = Depends(get_db),
) -> IntegrationReliabilityDetail:
    try:
        return reliability_service.integration_detail(db, integration_id, window_hours=window_hours)
    except DatabaseUnavailableError:
        raise database_unavailable() from None


@router.get("/failures", response_model=list[FailureItem])
def recent_failures(
    provider: IntegrationProvider | None = Query(default=None),
    integration_id: UUID | None = Query(default=None),
    source: FailureSource | None = Query(default=None),
    include_simulated: bool = Query(default=False),
    window_hours: int = Query(default=rules.MAX_WINDOW_HOURS, ge=rules.MIN_WINDOW_HOURS, le=rules.MAX_WINDOW_HOURS),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[FailureItem]:
    """Normalized failures, newest first. Failure Lab simulations are opt-in."""
    try:
        return reliability_service.failures(
            db,
            window_hours=window_hours,
            provider=provider.value if provider else None,
            integration_id=integration_id,
            source=source,
            include_simulated=include_simulated,
            limit=limit,
        )
    except DatabaseUnavailableError:
        raise database_unavailable() from None


@router.get("/request-metrics", response_model=RequestMetricsResponse)
def request_metrics(
    provider: IntegrationProvider | None = Query(default=None),
    integration_id: UUID | None = Query(default=None),
    is_simulated: bool | None = Query(default=None),
    window_hours: int = WindowHours,
    db: Session = Depends(get_db),
) -> RequestMetricsResponse:
    try:
        return reliability_service.request_metrics(
            db,
            window_hours=window_hours,
            provider=provider.value if provider else None,
            integration_id=integration_id,
            is_simulated=is_simulated,
        )
    except DatabaseUnavailableError:
        raise database_unavailable() from None
