"""Queries over SDK-reported telemetry events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models.integration import IntegrationORM
from app.db.models.telemetry import TelemetryEventORM


@dataclass(frozen=True)
class TelemetryAggregate:
    request_count: int
    success_count: int
    average_latency_ms: int | None
    p95_latency_ms: int | None


@dataclass(frozen=True)
class LatestTelemetry:
    occurred_at: datetime
    status_code: int | None
    error_category: str | None
    duration_ms: int
    route_template: str
    service: str
    method: str


class TelemetryRepository:
    def insert_new(
        self, session: Session, rows: list[dict]
    ) -> set[UUID]:
        """Insert rows, ignoring conflicts on (integration_id, event_id)."""
        if not rows:
            return set()
        statement = (
            pg_insert(TelemetryEventORM)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_telemetry_events_integration_event")
            .returning(TelemetryEventORM.event_id)
        )
        return {row[0] for row in session.execute(statement).all()}

    def aggregates(self, session: Session, *, since: datetime) -> dict[UUID, TelemetryAggregate]:
        success = and_(
            TelemetryEventORM.status_code >= 200,
            TelemetryEventORM.status_code <= 399,
            TelemetryEventORM.error_category.is_(None),
        )
        statement = (
            select(
                TelemetryEventORM.integration_id,
                func.count(),
                func.count().filter(success),
                func.avg(TelemetryEventORM.duration_ms),
                func.percentile_disc(0.95).within_group(TelemetryEventORM.duration_ms.asc()),
            )
            .where(
                TelemetryEventORM.occurred_at >= since,
                TelemetryEventORM.provenance == "sdk_reported",
            )
            .group_by(TelemetryEventORM.integration_id)
        )
        result: dict[UUID, TelemetryAggregate] = {}
        for integration_id, count, success_count, average, p95 in session.execute(statement).all():
            if not count:
                continue
            result[integration_id] = TelemetryAggregate(
                request_count=int(count),
                success_count=int(success_count),
                average_latency_ms=round(float(average)) if average is not None else None,
                p95_latency_ms=int(p95) if p95 is not None else None,
            )
        return result

    def latest_in_window(self, session: Session, *, since: datetime) -> dict[UUID, LatestTelemetry]:
        statement = (
            select(TelemetryEventORM)
            .where(
                TelemetryEventORM.occurred_at >= since,
                TelemetryEventORM.provenance == "sdk_reported",
            )
            .ext(distinct_on(TelemetryEventORM.integration_id))
            .order_by(
                TelemetryEventORM.integration_id,
                TelemetryEventORM.occurred_at.desc(),
                TelemetryEventORM.event_id.desc(),
            )
        )
        found: dict[UUID, LatestTelemetry] = {}
        for row in session.scalars(statement).all():
            found[row.integration_id] = LatestTelemetry(
                occurred_at=row.occurred_at,
                status_code=row.status_code,
                error_category=row.error_category,
                duration_ms=row.duration_ms,
                route_template=row.route_template,
                service=row.service,
                method=row.method,
            )
        return found

    def last_occurred(self, session: Session) -> dict[UUID, datetime]:
        statement = (
            select(TelemetryEventORM.integration_id, func.max(TelemetryEventORM.occurred_at))
            .where(TelemetryEventORM.provenance == "sdk_reported")
            .group_by(TelemetryEventORM.integration_id)
        )
        return {row[0]: row[1] for row in session.execute(statement).all()}

    def integrations_with_events_before(self, session: Session, *, before: datetime) -> set[UUID]:
        statement = (
            select(TelemetryEventORM.integration_id)
            .where(TelemetryEventORM.occurred_at < before)
            .distinct()
        )
        return set(session.scalars(statement).all())

    def category_counts(self, session: Session, *, since: datetime) -> dict[UUID, dict[str, int]]:
        statement = (
            select(
                TelemetryEventORM.integration_id,
                TelemetryEventORM.error_category,
                func.count(),
            )
            .where(
                TelemetryEventORM.occurred_at >= since,
                TelemetryEventORM.error_category.is_not(None),
                TelemetryEventORM.provenance == "sdk_reported",
            )
            .group_by(TelemetryEventORM.integration_id, TelemetryEventORM.error_category)
        )
        grouped: dict[UUID, dict[str, int]] = {}
        for integration_id, category, count in session.execute(statement).all():
            grouped.setdefault(integration_id, {})[str(category)] = int(count)
        return grouped

    def count_window(self, session: Session, *, since: datetime) -> tuple[int, int]:
        """Return (observations, errors) inside the window."""
        error = TelemetryEventORM.error_category.is_not(None)
        statement = select(func.count(), func.count().filter(error)).where(
            TelemetryEventORM.occurred_at >= since,
            TelemetryEventORM.provenance == "sdk_reported",
        )
        total, errors = session.execute(statement).one()
        return int(total or 0), int(errors or 0)

    def failed_events(
        self,
        session: Session,
        *,
        since: datetime,
        integration_id: UUID | None,
        provider: str | None,
        limit: int,
    ) -> list[TelemetryEventORM]:
        statement = (
            select(TelemetryEventORM)
            .join(IntegrationORM, IntegrationORM.id == TelemetryEventORM.integration_id)
            .where(
                TelemetryEventORM.occurred_at >= since,
                TelemetryEventORM.error_category.is_not(None),
                TelemetryEventORM.provenance == "sdk_reported",
            )
            .order_by(TelemetryEventORM.occurred_at.desc(), TelemetryEventORM.event_id.desc())
            .limit(limit)
        )
        if integration_id is not None:
            statement = statement.where(TelemetryEventORM.integration_id == integration_id)
        if provider is not None:
            statement = statement.where(IntegrationORM.provider == provider)
        return list(session.scalars(statement).all())

    def recent_for_integration(
        self,
        session: Session,
        *,
        integration_id: UUID,
        since: datetime,
        limit: int,
    ) -> list[TelemetryEventORM]:
        statement = (
            select(TelemetryEventORM)
            .where(
                TelemetryEventORM.integration_id == integration_id,
                TelemetryEventORM.occurred_at >= since,
            )
            .order_by(TelemetryEventORM.occurred_at.desc(), TelemetryEventORM.event_id.desc())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def page(
        self,
        session: Session,
        *,
        integration_id: UUID,
        limit: int,
        cursor_received_at: datetime | None,
        cursor_event_id: UUID | None,
        service: str | None,
        status_code: int | None,
        error_category: str | None,
        occurred_after: datetime | None,
        occurred_before: datetime | None,
    ) -> list[TelemetryEventORM]:
        statement = select(TelemetryEventORM).where(
            TelemetryEventORM.integration_id == integration_id
        )
        if service is not None:
            statement = statement.where(TelemetryEventORM.service == service)
        if status_code is not None:
            statement = statement.where(TelemetryEventORM.status_code == status_code)
        if error_category is not None:
            statement = statement.where(TelemetryEventORM.error_category == error_category)
        if occurred_after is not None:
            statement = statement.where(TelemetryEventORM.occurred_at >= occurred_after)
        if occurred_before is not None:
            statement = statement.where(TelemetryEventORM.occurred_at <= occurred_before)
        if cursor_received_at is not None and cursor_event_id is not None:
            statement = statement.where(
                tuple_(TelemetryEventORM.received_at, TelemetryEventORM.event_id)
                < tuple_(cursor_received_at, cursor_event_id)
            )
        statement = statement.order_by(
            TelemetryEventORM.received_at.desc(),
            TelemetryEventORM.event_id.desc(),
        ).limit(limit)
        return list(session.scalars(statement).all())


telemetry_repository = TelemetryRepository()
