"""Read-only aggregate queries for reliability evidence.

Every method is a single grouped query (no per-integration loops), so the
overview costs a fixed handful of queries regardless of integration count.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.diagnostics import DiagnosticCheckORM, DiagnosticRunORM
from app.db.models.failure_lab import FailureLabRunORM
from app.db.models.integration import IntegrationORM
from app.db.models.oauth import OAuthCredentialORM, ProviderRequestLogORM
from app.db.models.webhook import WebhookEventORM, WebhookProcessingAttemptORM

Log = ProviderRequestLogORM
Event = WebhookEventORM
Attempt = WebhookProcessingAttemptORM

# A request counts as successful only with an HTTP response < 400 and no error code.
_REQUEST_SUCCESS = and_(
    Log.error_message.is_(None),
    Log.status_code.is_not(None),
    Log.status_code < 400,
)


@dataclass(frozen=True)
class RequestAggregate:
    request_count: int
    success_count: int
    average_latency_ms: int | None
    p95_latency_ms: int | None


@dataclass(frozen=True)
class LatestRequest:
    timestamp: datetime
    endpoint: str
    status_code: int | None
    error_code: str | None
    latency_ms: int
    rate_limit_remaining: int | None


@dataclass(frozen=True)
class WebhookAggregate:
    events_total: int
    events_in_window: int
    duplicate_deliveries: int
    pending: int
    stale_pending: int
    processing: int
    stale_processing: int
    retry_scheduled: int
    failed: int
    processed: int
    ignored: int
    dismissed: int
    last_received_at: datetime | None


@dataclass(frozen=True)
class FailingCheck:
    check_code: str
    title: str
    evidence: str


@dataclass(frozen=True)
class AttemptAggregate:
    failed: int
    succeeded: int
    retries_scheduled: int


def _request_filters(
    *,
    since: datetime | None,
    provider: str | None,
    integration_id: UUID | None,
    is_simulated: bool | None,
) -> list:
    clauses = []
    if since is not None:
        clauses.append(Log.timestamp >= since)
    if provider:
        clauses.append(Log.provider == provider)
    if integration_id is not None:
        clauses.append(Log.integration_id == integration_id)
    if is_simulated is not None:
        clauses.append(Log.is_simulated.is_(is_simulated))
    return clauses


class ReliabilityRepository:
    # ------------------------------------------------------------ requests

    def request_aggregates(
        self,
        session: Session,
        *,
        since: datetime,
        provider: str | None = None,
        integration_id: UUID | None = None,
        is_simulated: bool | None = False,
        by_integration: bool = True,
    ) -> dict[UUID | None, RequestAggregate]:
        """count / success / avg / p95 (nearest-rank via percentile_disc) per integration."""
        columns = [
            func.count(Log.id),
            func.count(Log.id).filter(_REQUEST_SUCCESS),
            func.avg(Log.latency_ms),
            func.percentile_disc(0.95).within_group(Log.latency_ms.asc()),
        ]
        key_col = Log.integration_id if by_integration else None
        statement = select(*([key_col] if key_col is not None else []), *columns).where(
            *_request_filters(
                since=since, provider=provider, integration_id=integration_id, is_simulated=is_simulated
            )
        )
        if key_col is not None:
            statement = statement.group_by(key_col)

        result: dict[UUID | None, RequestAggregate] = {}
        for row in session.execute(statement).all():
            key, values = (row[0], row[1:]) if key_col is not None else (None, row)
            count, success, avg, p95 = values
            if not count:
                continue
            result[key] = RequestAggregate(
                request_count=int(count),
                success_count=int(success),
                average_latency_ms=round(float(avg)) if avg is not None else None,
                p95_latency_ms=int(p95) if p95 is not None else None,
            )
        return result

    def latest_requests(
        self,
        session: Session,
        *,
        since: datetime | None,
        provider: str | None = None,
        integration_id: UUID | None = None,
        is_simulated: bool | None = False,
    ) -> dict[UUID | None, LatestRequest]:
        """Most recent request per integration (DISTINCT ON)."""
        statement = (
            select(Log)
            .where(
                *_request_filters(
                    since=since,
                    provider=provider,
                    integration_id=integration_id,
                    is_simulated=is_simulated,
                )
            )
            .distinct(Log.integration_id)
            .order_by(Log.integration_id, Log.timestamp.desc(), Log.id.desc())
        )
        return {
            row.integration_id: LatestRequest(
                timestamp=row.timestamp,
                endpoint=row.endpoint,
                status_code=row.status_code,
                error_code=row.error_message,
                latency_ms=row.latency_ms,
                rate_limit_remaining=row.rate_limit_remaining,
            )
            for row in session.scalars(statement).all()
        }

    def latest_rate_limits(
        self, session: Session, *, since: datetime, provider: str = "github"
    ) -> dict[UUID | None, int]:
        statement = (
            select(Log.integration_id, Log.rate_limit_remaining)
            .where(
                Log.timestamp >= since,
                Log.provider == provider,
                Log.is_simulated.is_(False),
                Log.rate_limit_remaining.is_not(None),
            )
            .distinct(Log.integration_id)
            .order_by(Log.integration_id, Log.timestamp.desc())
        )
        return {key: int(value) for key, value in session.execute(statement).all()}

    def last_real_activity(self, session: Session) -> dict[UUID | None, datetime]:
        statement = (
            select(Log.integration_id, func.max(Log.timestamp))
            .where(Log.is_simulated.is_(False))
            .group_by(Log.integration_id)
        )
        return {key: ts for key, ts in session.execute(statement).all()}

    def failed_requests(
        self,
        session: Session,
        *,
        since: datetime,
        provider: str | None,
        integration_id: UUID | None,
        is_simulated: bool,
        limit: int,
    ) -> list[ProviderRequestLogORM]:
        statement = (
            select(Log)
            .where(
                ~_REQUEST_SUCCESS,
                *_request_filters(
                    since=since,
                    provider=provider,
                    integration_id=integration_id,
                    is_simulated=is_simulated,
                ),
            )
            .order_by(Log.timestamp.desc())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def recent_requests(
        self, session: Session, *, integration_id: UUID, since: datetime, limit: int
    ) -> list[ProviderRequestLogORM]:
        statement = (
            select(Log)
            .where(Log.integration_id == integration_id, Log.timestamp >= since)
            .order_by(Log.timestamp.desc())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def count_simulated_requests(self, session: Session, *, since: datetime) -> int:
        return int(
            session.scalar(
                select(func.count(Log.id)).where(Log.timestamp >= since, Log.is_simulated.is_(True))
            )
            or 0
        )

    # ------------------------------------------------------------ webhooks

    def webhook_aggregates(
        self,
        session: Session,
        *,
        since: datetime,
        now: datetime,
        stale_processing_after: timedelta,
        stale_pending_after: timedelta,
    ) -> dict[UUID, WebhookAggregate]:
        status = Event.processing_status
        pending_since = func.coalesce(Event.next_attempt_at, Event.first_received_at)
        statement = select(
            Event.integration_id,
            func.count(Event.id),
            func.count(Event.id).filter(Event.first_received_at >= since),
            func.coalesce(func.sum(Event.delivery_count - 1), 0),
            func.count(Event.id).filter(status == "pending"),
            func.count(Event.id).filter(
                status == "pending", pending_since < now - stale_pending_after
            ),
            func.count(Event.id).filter(status == "processing"),
            func.count(Event.id).filter(
                status == "processing",
                Event.processing_started_at < now - stale_processing_after,
            ),
            func.count(Event.id).filter(status == "retry_scheduled"),
            func.count(Event.id).filter(status == "failed"),
            func.count(Event.id).filter(status == "processed"),
            func.count(Event.id).filter(status == "ignored"),
            func.count(Event.id).filter(status == "dismissed"),
            func.max(Event.last_received_at),
        ).group_by(Event.integration_id)
        return {
            row[0]: WebhookAggregate(*[int(v) for v in row[1:13]], last_received_at=row[13])
            for row in session.execute(statement).all()
        }

    def attempt_aggregates(self, session: Session, *, since: datetime) -> dict[UUID, AttemptAggregate]:
        statement = (
            select(
                Event.integration_id,
                func.count(Attempt.id).filter(Attempt.outcome.in_(("failed", "abandoned"))),
                func.count(Attempt.id).filter(Attempt.outcome.in_(("succeeded", "ignored"))),
                func.count(Attempt.id).filter(Attempt.scheduled_delay_seconds.is_not(None)),
            )
            .join(Event, Event.id == Attempt.webhook_event_id)
            .where(Attempt.started_at >= since)
            .group_by(Event.integration_id)
        )
        return {
            row[0]: AttemptAggregate(failed=int(row[1]), succeeded=int(row[2]), retries_scheduled=int(row[3]))
            for row in session.execute(statement).all()
        }

    def failing_webhook_events(
        self,
        session: Session,
        *,
        since: datetime,
        integration_id: UUID | None,
        limit: int,
    ) -> list[tuple[WebhookEventORM, datetime]]:
        """Failed / retry-scheduled events with the time of their latest failed attempt."""
        last_failure = (
            select(
                Attempt.webhook_event_id.label("event_id"),
                func.max(Attempt.finished_at).label("last_failed_at"),
            )
            .where(Attempt.outcome.in_(("failed", "abandoned")))
            .group_by(Attempt.webhook_event_id)
            .subquery()
        )
        occurred = func.coalesce(Event.failed_at, last_failure.c.last_failed_at, Event.last_received_at)
        statement = (
            select(Event, occurred)
            .outerjoin(last_failure, last_failure.c.event_id == Event.id)
            .where(Event.processing_status.in_(("failed", "retry_scheduled")), occurred >= since)
            .order_by(occurred.desc())
            .limit(limit)
        )
        if integration_id is not None:
            statement = statement.where(Event.integration_id == integration_id)
        return [(event, ts) for event, ts in session.execute(statement).all()]

    def recent_webhook_events(
        self, session: Session, *, integration_id: UUID, limit: int
    ) -> list[WebhookEventORM]:
        statement = (
            select(Event)
            .where(Event.integration_id == integration_id)
            .order_by(Event.last_received_at.desc())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    # ------------------------------------------------------------ other evidence

    def integrations(self, session: Session) -> list[IntegrationORM]:
        return list(session.scalars(select(IntegrationORM).order_by(IntegrationORM.created_at)).all())

    def credential_integration_ids(self, session: Session) -> set[UUID]:
        return set(session.scalars(select(OAuthCredentialORM.integration_id)).all())

    def latest_diagnostic_runs(self, session: Session) -> dict[UUID, DiagnosticRunORM]:
        statement = (
            select(DiagnosticRunORM)
            .distinct(DiagnosticRunORM.integration_id)
            .order_by(DiagnosticRunORM.integration_id, DiagnosticRunORM.started_at.desc())
        )
        return {run.integration_id: run for run in session.scalars(statement).all()}

    def failure_lab_runs(
        self,
        session: Session,
        *,
        since: datetime,
        provider: str | None,
        integration_id: UUID | None,
        limit: int,
    ) -> list[FailureLabRunORM]:
        statement = (
            select(FailureLabRunORM)
            .where(FailureLabRunORM.created_at >= since)
            .order_by(FailureLabRunORM.created_at.desc())
            .limit(limit)
        )
        if provider:
            statement = statement.where(FailureLabRunORM.provider == provider)
        if integration_id is not None:
            statement = statement.where(FailureLabRunORM.integration_id == integration_id)
        return list(session.scalars(statement).all())

    def count_failure_lab_runs(self, session: Session, *, since: datetime) -> int:
        return int(
            session.scalar(select(func.count(FailureLabRunORM.id)).where(FailureLabRunORM.created_at >= since))
            or 0
        )

    def failed_diagnostic_runs(
        self,
        session: Session,
        *,
        since: datetime,
        provider: str | None,
        integration_id: UUID | None,
        limit: int,
    ) -> list[tuple[DiagnosticRunORM, FailingCheck | None]]:
        """Runs with overall_status=fail plus their first failing check."""
        first_fail = (
            select(DiagnosticCheckORM)
            .where(DiagnosticCheckORM.status == "fail")
            .distinct(DiagnosticCheckORM.diagnostic_run_id)
            .order_by(DiagnosticCheckORM.diagnostic_run_id, DiagnosticCheckORM.position)
            .subquery()
        )
        statement = (
            select(DiagnosticRunORM, first_fail.c.check_code, first_fail.c.title, first_fail.c.evidence)
            .outerjoin(first_fail, first_fail.c.diagnostic_run_id == DiagnosticRunORM.id)
            .where(DiagnosticRunORM.overall_status == "fail", DiagnosticRunORM.started_at >= since)
            .order_by(DiagnosticRunORM.started_at.desc())
            .limit(limit)
        )
        if provider:
            statement = statement.where(DiagnosticRunORM.provider == provider)
        if integration_id is not None:
            statement = statement.where(DiagnosticRunORM.integration_id == integration_id)
        return [
            (run, FailingCheck(code, title, evidence) if code else None)
            for run, code, title, evidence in session.execute(statement).all()
        ]

    def count_diagnostic_runs(self, session: Session, *, since: datetime) -> int:
        return int(
            session.scalar(
                select(func.count(DiagnosticRunORM.id)).where(DiagnosticRunORM.started_at >= since)
            )
            or 0
        )

    def webhook_window_totals(self, session: Session, *, since: datetime) -> tuple[int, int]:
        received, duplicates = session.execute(
            select(
                func.count(Event.id),
                func.coalesce(func.sum(Event.delivery_count - 1), 0),
            ).where(or_(Event.first_received_at >= since, Event.last_received_at >= since))
        ).one()
        return int(received), int(duplicates)


reliability_repository = ReliabilityRepository()
