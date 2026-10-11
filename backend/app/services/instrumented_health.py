"""Map stored SDK observations into the pure instrumented-HTTP health rules."""

from __future__ import annotations

from app.models.telemetry import TelemetryFailureCategory, TelemetryObservationMetrics
from app.repositories.telemetry import LatestTelemetry, TelemetryAggregate
from app.services import reliability_rules as rules
from app.services.health_evaluator import (
    HealthAssessment,
    TelemetryEvidence,
    evaluate_instrumented_http,
)


def assess_instrumented(
    *,
    aggregate: TelemetryAggregate | None,
    latest: LatestTelemetry | None,
    categories: dict[str, int],
    active_credentials: int,
    has_older_observations: bool,
    window_hours: int,
) -> tuple[HealthAssessment, TelemetryObservationMetrics]:
    count = aggregate.request_count if aggregate else 0
    success = aggregate.success_count if aggregate else 0
    errors = count - success
    error_rate = round(errors / count, 4) if count else None
    p95 = None
    average = None
    if aggregate is not None and count:
        average = aggregate.average_latency_ms
        if count >= rules.INSTRUMENTED_MIN_SAMPLE_FOR_P95:
            p95 = aggregate.p95_latency_ms
    ordered = tuple(sorted(categories.items(), key=lambda item: (-item[1], item[0])))
    evidence = TelemetryEvidence(
        active_credentials=active_credentials,
        observation_count=count,
        success_count=success,
        error_count=errors,
        error_rate=error_rate,
        average_latency_ms=average,
        p95_latency_ms=p95,
        latest_occurred_at=latest.occurred_at if latest else None,
        latest_status_code=latest.status_code if latest else None,
        latest_error_category=latest.error_category if latest else None,
        latest_duration_ms=latest.duration_ms if latest else None,
        latest_route_template=latest.route_template if latest else None,
        latest_service=latest.service if latest else None,
        latest_method=latest.method if latest else None,
        failure_categories=ordered,
        has_older_observations=has_older_observations,
        window_hours=window_hours,
    )
    assessment = evaluate_instrumented_http(evidence)
    metrics = TelemetryObservationMetrics(
        request_count=count,
        success_count=success,
        error_count=errors,
        error_rate=error_rate,
        sample_count=count,
        average_latency_ms=average,
        p95_latency_ms=p95,
        latest_occurred_at=evidence.latest_occurred_at,
        latest_status_code=evidence.latest_status_code,
        latest_error_category=evidence.latest_error_category,
        latest_duration_ms=evidence.latest_duration_ms,
        latest_route_template=evidence.latest_route_template,
        latest_service=evidence.latest_service,
        failure_categories=[
            TelemetryFailureCategory(category=category, count=category_count)
            for category, category_count in ordered
        ],
    )
    return assessment, metrics

