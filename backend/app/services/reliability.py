"""Reliability read path: persisted evidence -> deterministic evaluator -> API models.

Passive only: nothing here calls a provider. Loading the dashboard must never
spend GitHub quota — active checks live in the diagnostics service.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.db.models.integration import IntegrationORM
from app.db.models.oauth import ProviderRequestLogORM
from app.models.github import ProviderRequestLogResponse
from app.models.integration import IntegrationProvider
from app.models.reliability import (
    DiagnosticRunBrief,
    FailureItem,
    FailureSource,
    HealthState,
    HealthTotals,
    IntegrationHealth,
    IntegrationReliabilityDetail,
    OperationalMetrics,
    ReliabilityOverview,
    RequestMetrics,
    RequestMetricsResponse,
    SystemHealth,
    WebhookMetrics,
)
from app.models.webhook import WebhookEventSummary
from app.repositories.reliability import (
    AttemptAggregate,
    LatestRequest,
    RequestAggregate,
    WebhookAggregate,
    reliability_repository as repo,
)
from app.services import reliability_rules as rules
from app.services.health_evaluator import (
    GitHubEvidence,
    HealthAssessment,
    StripeEvidence,
    evaluate_github,
    evaluate_stripe,
)

logger = logging.getLogger(__name__)

OVERVIEW_FAILURE_LIMIT = 10
DETAIL_LIST_LIMIT = 20

_CONNECTION_LABELS = {
    "connected": "Connected",
    "needs_setup": "Needs setup",
    "not_connected": "Not connected",
}


class DatabaseUnavailableError(RuntimeError):
    pass


def database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"message": "Database unavailable", "database": HealthState.FAILED.value},
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_request_metrics(
    aggregate: RequestAggregate | None,
    latest: LatestRequest | None,
    rate_limit_remaining: int | None = None,
) -> RequestMetrics:
    metrics = RequestMetrics()
    if aggregate is not None:
        failures = aggregate.request_count - aggregate.success_count
        metrics = RequestMetrics(
            request_count=aggregate.request_count,
            success_count=aggregate.success_count,
            failure_count=failures,
            error_rate=round(failures / aggregate.request_count, 4),
            average_latency_ms=aggregate.average_latency_ms,
            p95_latency_ms=aggregate.p95_latency_ms,
        )
    if latest is not None:
        metrics = metrics.model_copy(
            update={
                "latest_latency_ms": latest.latency_ms,
                "latest_latency_band": rules.latency_band(latest.latency_ms),
                "latest_status_code": latest.status_code,
                "latest_error_code": latest.error_code,
                "latest_endpoint": latest.endpoint,
                "latest_request_at": latest.timestamp,
                "rate_limit_remaining": rate_limit_remaining
                if rate_limit_remaining is not None
                else latest.rate_limit_remaining,
            }
        )
    return metrics


def build_webhook_metrics(
    configured: bool, aggregate: WebhookAggregate | None, attempts: AttemptAggregate | None
) -> WebhookMetrics:
    metrics = WebhookMetrics(verification_configured=configured)
    if aggregate is not None:
        metrics = metrics.model_copy(update=asdict(aggregate))
    if attempts is not None:
        metrics = metrics.model_copy(
            update={
                "failed_attempts_in_window": attempts.failed,
                "successful_attempts_in_window": attempts.succeeded,
                "retries_scheduled_in_window": attempts.retries_scheduled,
            }
        )
    return metrics


class ReliabilityService:
    # ------------------------------------------------------------- system

    def system(self, session: Session) -> SystemHealth:
        now = _utcnow()
        try:
            check_database_connection(session)
        except SQLAlchemyError:
            session.rollback()
            logger.warning("Reliability system check: database unreachable")
            return SystemHealth(database=HealthState.FAILED, checked_at=now)
        return SystemHealth(database=HealthState.HEALTHY, checked_at=now)

    # ------------------------------------------------------------- overview

    def overview(
        self,
        session: Session,
        *,
        window_hours: int = rules.DEFAULT_WINDOW_HOURS,
        now: datetime | None = None,
    ) -> ReliabilityOverview:
        now = now or _utcnow()
        since = now - timedelta(hours=window_hours)
        try:
            check_database_connection(session)
            healths = self._integration_healths(session, since=since, now=now, window_hours=window_hours)
            failures = self._failures(
                session,
                since=since,
                provider=None,
                integration_id=None,
                source=None,
                include_simulated=False,
                limit=OVERVIEW_FAILURE_LIMIT,
            )
            operational = self._operational(session, since=since, healths=healths)
        except SQLAlchemyError as exc:
            session.rollback()
            logger.warning("Reliability overview unavailable: database error")
            raise DatabaseUnavailableError from exc

        totals = HealthTotals()
        for item in healths:
            setattr(totals, item.health.value, getattr(totals, item.health.value) + 1)

        return ReliabilityOverview(
            generated_at=now,
            window_hours=window_hours,
            system=SystemHealth(database=HealthState.HEALTHY, checked_at=now),
            totals=totals,
            integrations=healths,
            recent_failures=failures,
            operational=operational,
        )

    def integration_detail(
        self,
        session: Session,
        integration_id: UUID,
        *,
        window_hours: int = rules.DEFAULT_WINDOW_HOURS,
        now: datetime | None = None,
    ) -> IntegrationReliabilityDetail:
        now = now or _utcnow()
        since = now - timedelta(hours=window_hours)
        try:
            if session.get(IntegrationORM, integration_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Integration not found")
            health = next(
                h
                for h in self._integration_healths(session, since=since, now=now, window_hours=window_hours)
                if h.integration_id == integration_id
            )
            requests = repo.recent_requests(
                session, integration_id=integration_id, since=since, limit=DETAIL_LIST_LIMIT
            )
            events = (
                repo.recent_webhook_events(session, integration_id=integration_id, limit=DETAIL_LIST_LIMIT)
                if health.provider == IntegrationProvider.STRIPE.value
                else []
            )
            failures = self._failures(
                session,
                since=since,
                provider=None,
                integration_id=integration_id,
                source=None,
                include_simulated=False,
                limit=DETAIL_LIST_LIMIT,
            )
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabaseUnavailableError from exc

        return IntegrationReliabilityDetail(
            **health.model_dump(),
            generated_at=now,
            window_hours=window_hours,
            recent_requests=[ProviderRequestLogResponse.model_validate(r) for r in requests],
            recent_webhook_events=[WebhookEventSummary.model_validate(e) for e in events],
            recent_failures=failures,
        )

    def failures(
        self,
        session: Session,
        *,
        window_hours: int,
        provider: str | None,
        integration_id: UUID | None,
        source: FailureSource | None,
        include_simulated: bool,
        limit: int,
        now: datetime | None = None,
    ) -> list[FailureItem]:
        since = (now or _utcnow()) - timedelta(hours=window_hours)
        try:
            return self._failures(
                session,
                since=since,
                provider=provider,
                integration_id=integration_id,
                source=source,
                include_simulated=include_simulated,
                limit=limit,
            )
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabaseUnavailableError from exc

    def request_metrics(
        self,
        session: Session,
        *,
        window_hours: int,
        provider: str | None,
        integration_id: UUID | None,
        is_simulated: bool | None,
        now: datetime | None = None,
    ) -> RequestMetricsResponse:
        since = (now or _utcnow()) - timedelta(hours=window_hours)
        try:
            aggregate = repo.request_aggregates(
                session,
                since=since,
                provider=provider,
                integration_id=integration_id,
                is_simulated=is_simulated,
                by_integration=False,
            ).get(None)
            latest_row = session.scalars(
                select(ProviderRequestLogORM)
                .where(
                    ProviderRequestLogORM.timestamp >= since,
                    *([ProviderRequestLogORM.provider == provider] if provider else []),
                    *(
                        [ProviderRequestLogORM.integration_id == integration_id]
                        if integration_id
                        else []
                    ),
                    *(
                        [ProviderRequestLogORM.is_simulated.is_(is_simulated)]
                        if is_simulated is not None
                        else []
                    ),
                )
                .order_by(ProviderRequestLogORM.timestamp.desc())
                .limit(1)
            ).first()
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabaseUnavailableError from exc

        latest = (
            LatestRequest(
                timestamp=latest_row.timestamp,
                endpoint=latest_row.endpoint,
                status_code=latest_row.status_code,
                error_code=latest_row.error_message,
                latency_ms=latest_row.latency_ms,
                rate_limit_remaining=latest_row.rate_limit_remaining,
            )
            if latest_row
            else None
        )
        return RequestMetricsResponse(
            window_hours=window_hours,
            provider=provider,
            integration_id=integration_id,
            is_simulated=is_simulated,
            metrics=build_request_metrics(aggregate, latest),
        )

    # ------------------------------------------------------------- internals

    def _integration_healths(
        self, session: Session, *, since: datetime, now: datetime, window_hours: int
    ) -> list[IntegrationHealth]:
        integrations = repo.integrations(session)
        request_aggs = repo.request_aggregates(session, since=since, is_simulated=False)
        latest = repo.latest_requests(session, since=since, is_simulated=False)
        rate_limits = repo.latest_rate_limits(session, since=since)
        activity = repo.last_real_activity(session)
        credentials = repo.credential_integration_ids(session)
        webhook_aggs = repo.webhook_aggregates(
            session,
            since=since,
            now=now,
            stale_processing_after=timedelta(minutes=rules.STALE_PROCESSING_MINUTES),
            stale_pending_after=timedelta(minutes=rules.STALE_PENDING_MINUTES),
        )
        attempt_aggs = repo.attempt_aggregates(session, since=since)
        diagnostics = repo.latest_diagnostic_runs(session)
        secret_configured = bool(get_settings().stripe_webhook_secret)

        results: list[IntegrationHealth] = []
        for integration in integrations:
            iid = integration.id
            request_metrics: RequestMetrics | None = None
            webhook_metrics: WebhookMetrics | None = None
            last_activity: datetime | None = None

            if integration.provider == IntegrationProvider.GITHUB.value:
                request_metrics = build_request_metrics(
                    request_aggs.get(iid), latest.get(iid), rate_limits.get(iid)
                )
                last_activity = activity.get(iid)
                assessment = evaluate_github(
                    GitHubEvidence(
                        connection_status=integration.status,
                        has_credential=iid in credentials,
                        metrics=request_metrics,
                        window_hours=window_hours,
                        last_activity_at=last_activity,
                    )
                )
                configuration = _CONNECTION_LABELS.get(integration.status, integration.status)
            elif integration.provider == IntegrationProvider.STRIPE.value:
                webhook_metrics = build_webhook_metrics(
                    secret_configured, webhook_aggs.get(iid), attempt_aggs.get(iid)
                )
                last_activity = webhook_metrics.last_received_at
                assessment = evaluate_stripe(
                    StripeEvidence(metrics=webhook_metrics, window_hours=window_hours)
                )
                configuration = (
                    "Webhook verification configured"
                    if secret_configured
                    else "Webhook verification not configured"
                )
            else:
                assessment = HealthAssessment(
                    HealthState.UNKNOWN, "No reliability rules exist for this provider yet."
                )
                configuration = integration.status

            run = diagnostics.get(iid)
            results.append(
                IntegrationHealth(
                    integration_id=iid,
                    name=integration.name,
                    provider=integration.provider,
                    connection_status=integration.status,
                    configuration=configuration,
                    health=assessment.health,
                    summary=assessment.summary,
                    evidence=assessment.evidence,
                    recommended_action=assessment.recommended_action,
                    last_activity_at=last_activity,
                    last_checked_at=integration.last_checked_at,
                    request_metrics=request_metrics,
                    webhook_metrics=webhook_metrics,
                    latest_diagnostic=DiagnosticRunBrief(
                        id=run.id,
                        overall_status=run.overall_status,
                        summary=run.summary,
                        started_at=run.started_at,
                        completed_at=run.completed_at,
                    )
                    if run
                    else None,
                )
            )
        return results

    def _operational(
        self, session: Session, *, since: datetime, healths: list[IntegrationHealth]
    ) -> OperationalMetrics:
        real = repo.request_aggregates(session, since=since, is_simulated=False, by_integration=False).get(None)
        received, duplicates = repo.webhook_window_totals(session, since=since)
        webhooks = [h.webhook_metrics for h in healths if h.webhook_metrics is not None]
        return OperationalMetrics(
            real_provider_requests=real.request_count if real else 0,
            real_provider_errors=(real.request_count - real.success_count) if real else 0,
            simulated_requests=repo.count_simulated_requests(session, since=since),
            failure_lab_runs=repo.count_failure_lab_runs(session, since=since),
            webhook_events_received=received,
            duplicate_webhook_deliveries=duplicates,
            webhook_processed=sum(w.processed for w in webhooks),
            webhook_retry_scheduled=sum(w.retry_scheduled for w in webhooks),
            webhook_failed=sum(w.failed for w in webhooks),
            webhook_pending=sum(w.pending for w in webhooks),
            diagnostic_runs=repo.count_diagnostic_runs(session, since=since),
        )

    def _failures(
        self,
        session: Session,
        *,
        since: datetime,
        provider: str | None,
        integration_id: UUID | None,
        source: FailureSource | None,
        include_simulated: bool,
        limit: int,
    ) -> list[FailureItem]:
        if source is not None:
            sources = {source}
        else:
            sources = {
                FailureSource.PROVIDER_REQUEST,
                FailureSource.WEBHOOK_PROCESSING,
                FailureSource.DIAGNOSTIC,
            }
            if include_simulated:
                sources.add(FailureSource.FAILURE_LAB)

        names = {i.id: i.name for i in repo.integrations(session)}
        items: list[FailureItem] = []

        if FailureSource.PROVIDER_REQUEST in sources:
            # Simulated request logs are represented by their Failure Lab run instead.
            for row in repo.failed_requests(
                session,
                since=since,
                provider=provider,
                integration_id=integration_id,
                is_simulated=False,
                limit=limit,
            ):
                code = rules.provider_failure_code(row.error_message, row.status_code)
                items.append(
                    FailureItem(
                        id=f"request:{row.id}",
                        source=FailureSource.PROVIDER_REQUEST,
                        integration_id=row.integration_id,
                        integration_name=names.get(row.integration_id),
                        provider=row.provider,
                        occurred_at=row.timestamp,
                        severity=rules.provider_failure_severity(code, row.status_code),
                        code=code,
                        summary=rules.provider_failure_summary(row.provider, code, row.status_code),
                        method=row.method,
                        endpoint=row.endpoint,
                        status_code=row.status_code,
                        latency_ms=row.latency_ms,
                    )
                )

        if FailureSource.WEBHOOK_PROCESSING in sources and provider in (None, "stripe"):
            for event, occurred_at in repo.failing_webhook_events(
                session, since=since, integration_id=integration_id, limit=limit
            ):
                failed = event.processing_status == "failed"
                code = event.last_error_code or "webhook_processing_error"
                items.append(
                    FailureItem(
                        id=f"webhook:{event.id}",
                        source=FailureSource.WEBHOOK_PROCESSING,
                        integration_id=event.integration_id,
                        integration_name=names.get(event.integration_id),
                        provider=event.provider,
                        occurred_at=occurred_at,
                        severity=rules.WEBHOOK_FAILED_SEVERITY if failed else rules.WEBHOOK_RETRY_SEVERITY,
                        code=code,
                        summary=rules.webhook_failure_summary(code, event.processing_status, event.event_type),
                        webhook_event_id=event.id,
                        event_type=event.event_type,
                        attempt_count=event.attempt_count,
                    )
                )

        if FailureSource.FAILURE_LAB in sources:
            for run in repo.failure_lab_runs(
                session, since=since, provider=provider, integration_id=integration_id, limit=limit
            ):
                items.append(
                    FailureItem(
                        id=f"failure_lab:{run.id}",
                        source=FailureSource.FAILURE_LAB,
                        integration_id=run.integration_id,
                        integration_name=names.get(run.integration_id),
                        provider=run.provider,
                        occurred_at=run.created_at,
                        severity=rules.SIMULATION_SEVERITY,
                        code=run.error_code or run.diagnosis_code,
                        summary=f"Simulation: {run.diagnosis_title}",
                        simulated=True,
                        method=run.method,
                        endpoint=run.endpoint,
                        status_code=run.status_code,
                        latency_ms=run.latency_ms,
                        diagnosis_title=run.diagnosis_title,
                        retryable=run.retryable,
                    )
                )

        if FailureSource.DIAGNOSTIC in sources:
            for run, check in repo.failed_diagnostic_runs(
                session, since=since, provider=provider, integration_id=integration_id, limit=limit
            ):
                items.append(
                    FailureItem(
                        id=f"diagnostic:{run.id}",
                        source=FailureSource.DIAGNOSTIC,
                        integration_id=run.integration_id,
                        integration_name=names.get(run.integration_id),
                        provider=run.provider,
                        occurred_at=run.completed_at or run.started_at,
                        severity=rules.DIAGNOSTIC_FAIL_SEVERITY,
                        code=check.check_code if check else "diagnostic_failed",
                        summary=f"Diagnostic check failed: {check.title}. {check.evidence}"
                        if check
                        else (run.summary or "Diagnostic run failed."),
                        diagnostic_run_id=run.id,
                    )
                )

        items.sort(key=lambda item: item.occurred_at, reverse=True)
        return items[:limit]


reliability_service = ReliabilityService()
