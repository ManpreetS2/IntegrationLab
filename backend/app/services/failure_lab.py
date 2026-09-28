"""Failure Lab orchestration: simulate → log → diagnose → persist (no real GitHub)."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.failure_lab import (
    DiagnosisResult,
    FailureLabRunListItem,
    FailureLabRunRequest,
    FailureLabRunResponse,
    FailureScenario,
    FailureScenarioInfo,
    ObservedResult,
    RequestInfo,
)
from app.models.integration import IntegrationProvider
from app.repositories.failure_lab import failure_lab_run_repository
from app.repositories.integrations import integration_repository
from app.repositories.oauth import (
    oauth_credential_repository,
    provider_request_log_repository,
)
from app.services.failure_diagnostics import failure_diagnosis_engine
from app.services.failure_simulator import provider_failure_simulator

logger = logging.getLogger(__name__)

SCENARIO_CATALOG: list[FailureScenarioInfo] = [
    FailureScenarioInfo(
        id=FailureScenario.UNAUTHORIZED_401,
        label="401 Unauthorized",
        description="Simulate an invalid/revoked credential response.",
    ),
    FailureScenarioInfo(
        id=FailureScenario.FORBIDDEN_403,
        label="403 Forbidden",
        description="Simulate a permission/access denial (quota remaining > 0).",
    ),
    FailureScenarioInfo(
        id=FailureScenario.NOT_FOUND_404,
        label="404 Not Found",
        description="Simulate a missing or hidden resource response.",
    ),
    FailureScenarioInfo(
        id=FailureScenario.RATE_LIMITED_429,
        label="429 Rate Limited",
        description="Simulate exhausted provider rate limits.",
    ),
    FailureScenarioInfo(
        id=FailureScenario.PROVIDER_500,
        label="500 Provider Error",
        description="Simulate a provider-side server failure.",
    ),
    FailureScenarioInfo(
        id=FailureScenario.TIMEOUT,
        label="Timeout",
        description="Simulate no HTTP response before timeout.",
    ),
    FailureScenarioInfo(
        id=FailureScenario.MALFORMED_JSON,
        label="Malformed JSON",
        description="Simulate HTTP 200 with an unparseable JSON body.",
    ),
    FailureScenarioInfo(
        id=FailureScenario.TRANSPORT_ERROR,
        label="Transport Error",
        description="Simulate connection refused/reset style failure.",
    ),
]


class FailureLabService:
    """Sandboxed failure reproduction. Never mutates real connection health."""

    def list_scenarios(self) -> list[FailureScenarioInfo]:
        return list(SCENARIO_CATALOG)

    def run(self, session: Session, payload: FailureLabRunRequest) -> FailureLabRunResponse:
        integration = integration_repository.get_by_id(session, payload.integration_id)
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        if integration.provider != IntegrationProvider.GITHUB.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failure Lab currently supports GitHub integrations only",
            )

        # Capture pre-run status to prove we never mutate connection health.
        status_before = integration.status
        last_checked_before = integration.last_checked_at
        credential_before = oauth_credential_repository.get_by_integration_id(
            session, integration.id
        )
        credential_cipher_before = (
            credential_before.access_token_encrypted if credential_before else None
        )

        observed = provider_failure_simulator.simulate(payload.scenario)
        method = provider_failure_simulator.METHOD
        endpoint = provider_failure_simulator.ENDPOINT

        try:
            provider_request_log_repository.create(
                session,
                integration_id=integration.id,
                provider="github",
                method=method,
                endpoint=endpoint,
                status_code=observed.status_code,
                latency_ms=observed.latency_ms,
                error_message=observed.error_code,
                rate_limit_remaining=observed.rate_limit_remaining,
                is_simulated=True,
                scenario=payload.scenario.value,
            )
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("Failed to persist simulated provider request log")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record simulated request",
            ) from None

        diagnosis = failure_diagnosis_engine.diagnose(observed)
        evidence_summary = " | ".join(diagnosis.evidence)
        checks_json = json.dumps(diagnosis.recommended_checks)

        try:
            run = failure_lab_run_repository.create(
                session,
                integration_id=integration.id,
                provider="github",
                scenario=payload.scenario.value,
                method=method,
                endpoint=endpoint,
                status_code=observed.status_code,
                latency_ms=observed.latency_ms,
                error_code=observed.error_code,
                diagnosis_code=diagnosis.code,
                diagnosis_title=diagnosis.title,
                diagnosis_summary=diagnosis.summary,
                retryable=diagnosis.retryable,
                evidence_summary=evidence_summary,
                recommended_checks=checks_json,
                rate_limit_remaining=observed.rate_limit_remaining,
            )
            session.commit()
            session.refresh(run)
        except Exception:
            session.rollback()
            logger.exception("Failed to persist Failure Lab run")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save Failure Lab run",
            ) from None

        # Safety: simulations never touch real connection state or credentials.
        session.refresh(integration)
        if integration.status != status_before or integration.last_checked_at != last_checked_before:
            logger.error("Failure Lab mutated integration status unexpectedly")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failure Lab safety check failed",
            )
        credential_after = oauth_credential_repository.get_by_integration_id(
            session, integration.id
        )
        cipher_after = credential_after.access_token_encrypted if credential_after else None
        if cipher_after != credential_cipher_before:
            logger.error("Failure Lab mutated OAuth credentials unexpectedly")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failure Lab safety check failed",
            )

        logger.info(
            "Failure Lab run %s scenario=%s integration=%s",
            run.id,
            payload.scenario.value,
            integration.id,
        )
        return self._to_response(run, diagnosis.evidence, diagnosis.recommended_checks)

    def list_runs(
        self,
        session: Session,
        *,
        integration_id: UUID | None = None,
        scenario: FailureScenario | None = None,
        limit: int = 25,
    ) -> list[FailureLabRunListItem]:
        rows = failure_lab_run_repository.list_recent(
            session,
            integration_id=integration_id,
            scenario=scenario.value if scenario else None,
            limit=limit,
        )
        return [
            FailureLabRunListItem(
                id=row.id,
                integration_id=row.integration_id,
                provider=row.provider,
                scenario=FailureScenario(row.scenario),
                status_code=row.status_code,
                latency_ms=row.latency_ms,
                error_code=row.error_code,
                diagnosis_code=row.diagnosis_code,
                diagnosis_title=row.diagnosis_title,
                retryable=row.retryable,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def get_run(self, session: Session, run_id: UUID) -> FailureLabRunResponse:
        row = failure_lab_run_repository.get_by_id(session, run_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failure Lab run not found")
        evidence = [part.strip() for part in (row.evidence_summary or "").split("|") if part.strip()]
        try:
            checks = json.loads(row.recommended_checks) if row.recommended_checks else []
            if not isinstance(checks, list):
                checks = []
            checks = [str(item) for item in checks]
        except json.JSONDecodeError:
            checks = []
        return self._to_response(row, evidence, checks)

    def _to_response(self, row, evidence: list[str], checks: list[str]) -> FailureLabRunResponse:
        return FailureLabRunResponse(
            id=row.id,
            integration_id=row.integration_id,
            provider=row.provider,
            scenario=FailureScenario(row.scenario),
            request=RequestInfo(method=row.method, endpoint=row.endpoint),
            observed=ObservedResult(
                status_code=row.status_code,
                latency_ms=row.latency_ms,
                error_code=row.error_code,
                rate_limit_remaining=row.rate_limit_remaining,
            ),
            diagnosis=DiagnosisResult(
                code=row.diagnosis_code,
                title=row.diagnosis_title,
                summary=row.diagnosis_summary,
                retryable=row.retryable,
                evidence=evidence,
                recommended_checks=checks,
            ),
            created_at=row.created_at,
        )


failure_lab_service = FailureLabService()
