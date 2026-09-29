"""Diagnostic run persistence, history, concurrency guard, and overall-status precedence."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from app.db.models.diagnostics import DiagnosticCheckORM, DiagnosticRunORM
from app.db.models.integration import IntegrationORM
from app.models.diagnostics import CheckStatus, DiagnosticRunStatus
from app.services import diagnostics as diagnostics_module
from app.services.diagnostic_checks import CheckResult, summarize_checks
from tests.reliability_helpers import github_integration

UNKNOWN_ID = "00000000-0000-0000-0000-000000000099"


def _check(status: CheckStatus, required: bool = False, code: str | None = None) -> CheckResult:
    return CheckResult(code or f"c_{uuid4().hex[:6]}", code or "Check", status, "evidence", required=required)


# ---------------------------------------------------------------- precedence


def test_required_failure_wins() -> None:
    status, summary = summarize_checks(
        [_check(CheckStatus.FAIL, True, "a"), _check(CheckStatus.WARNING), _check(CheckStatus.UNKNOWN, True)]
    )
    assert status == DiagnosticRunStatus.FAIL
    assert summary.startswith("1 required check(s) failed")


def test_warning_beats_unknown() -> None:
    status, _ = summarize_checks([_check(CheckStatus.WARNING), _check(CheckStatus.UNKNOWN, True)])
    assert status == DiagnosticRunStatus.WARNING


def test_non_required_failure_is_warning() -> None:
    status, _ = summarize_checks([_check(CheckStatus.PASS, True), _check(CheckStatus.FAIL)])
    assert status == DiagnosticRunStatus.WARNING


def test_required_unknown_is_unknown() -> None:
    status, summary = summarize_checks([_check(CheckStatus.PASS, True), _check(CheckStatus.UNKNOWN, True, "x")])
    assert status == DiagnosticRunStatus.UNKNOWN
    assert summary.startswith("Insufficient evidence")


def test_informational_unknown_still_passes() -> None:
    status, _ = summarize_checks([_check(CheckStatus.PASS, True), _check(CheckStatus.UNKNOWN)])
    assert status == DiagnosticRunStatus.PASS


def test_all_pass() -> None:
    status, summary = summarize_checks([_check(CheckStatus.PASS, True), _check(CheckStatus.PASS, True)])
    assert status == DiagnosticRunStatus.PASS
    assert summary == "All 2 required checks passed."


# ---------------------------------------------------------------- persistence


def test_run_and_checks_persisted(client, db_session) -> None:
    gh = github_integration(db_session)
    run = client.post(f"/api/diagnostics/{gh.id}/run").json()
    stored = db_session.get(DiagnosticRunORM, run["id"])
    assert stored is not None
    assert stored.overall_status == "fail"
    assert stored.provider == "github"
    assert stored.trigger == "manual"
    assert stored.completed_at >= stored.started_at
    checks = list(
        db_session.scalars(
            select(DiagnosticCheckORM)
            .where(DiagnosticCheckORM.diagnostic_run_id == stored.id)
            .order_by(DiagnosticCheckORM.position)
        ).all()
    )
    assert [c.position for c in checks] == list(range(1, len(checks) + 1))
    assert len({c.check_code for c in checks}) == len(checks)
    assert [c.check_code for c in checks] == [c["check_code"] for c in run["checks"]]


def test_history_newest_first_and_limited(client, db_session) -> None:
    gh = github_integration(db_session)
    ids = [client.post(f"/api/diagnostics/{gh.id}/run").json()["id"] for _ in range(3)]
    history = client.get(f"/api/diagnostics/{gh.id}/runs").json()
    assert [item["id"] for item in history] == list(reversed(ids))
    assert "checks" not in history[0]
    assert history[0]["check_counts"]["failed"] >= 1
    limited = client.get(f"/api/diagnostics/{gh.id}/runs", params={"limit": 2}).json()
    assert [item["id"] for item in limited] == list(reversed(ids))[:2]


@pytest.mark.parametrize("limit", [0, 51])
def test_history_limit_validation(client, db_session, limit) -> None:
    gh = github_integration(db_session)
    assert client.get(f"/api/diagnostics/{gh.id}/runs", params={"limit": limit}).status_code == 422


def test_history_scoped_to_integration(client, db_session, stripe_integration_id) -> None:
    gh = github_integration(db_session)
    client.post(f"/api/diagnostics/{gh.id}/run")
    assert client.get(f"/api/diagnostics/{stripe_integration_id}/runs").json() == []


def test_run_detail(client, db_session) -> None:
    gh = github_integration(db_session)
    run = client.post(f"/api/diagnostics/{gh.id}/run").json()
    detail = client.get(f"/api/diagnostics/runs/{run['id']}")
    assert detail.status_code == 200
    assert detail.json() == run


def test_unknown_ids_404(client) -> None:
    assert client.post(f"/api/diagnostics/{UNKNOWN_ID}/run").status_code == 404
    assert client.get(f"/api/diagnostics/{UNKNOWN_ID}/runs").status_code == 404
    assert client.get(f"/api/diagnostics/runs/{UNKNOWN_ID}").status_code == 404


def test_concurrent_run_rejected(client, db_session) -> None:
    gh = github_integration(db_session)
    db_session.add(
        DiagnosticRunORM(
            integration_id=gh.id,
            provider="github",
            trigger="manual",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            overall_status="running",
        )
    )
    db_session.commit()
    response = client.post(f"/api/diagnostics/{gh.id}/run")
    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_abandoned_running_run_does_not_block(client, db_session) -> None:
    gh = github_integration(db_session)
    db_session.add(
        DiagnosticRunORM(
            integration_id=gh.id,
            provider="github",
            trigger="manual",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            overall_status="running",
        )
    )
    db_session.commit()
    assert client.post(f"/api/diagnostics/{gh.id}/run").status_code == 200


def test_internal_error_recorded_as_unknown(client, db_session, monkeypatch, caplog) -> None:
    gh = github_integration(db_session)

    def explode(*args, **kwargs):
        raise RuntimeError("boom with gho_example_should_not_leak")

    monkeypatch.setattr(diagnostics_module, "run_github_checks", explode)
    response = client.post(f"/api/diagnostics/{gh.id}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "unknown"
    assert [c["check_code"] for c in body["checks"]] == ["diagnostic_execution"]
    assert "gho_" not in response.text
    assert f"Diagnostic check failed for integration {gh.id}" in caplog.text


def test_runs_cascade_when_integration_deleted(client, db_session) -> None:
    created = client.post("/api/integrations", json={"name": "Temp GitHub", "provider": "github"}).json()
    client.post(f"/api/diagnostics/{created['id']}/run")
    db_session.execute(delete(IntegrationORM).where(IntegrationORM.id == UUID(created["id"])))
    db_session.commit()
    assert db_session.scalars(select(DiagnosticRunORM)).all() == []
    assert db_session.scalars(select(DiagnosticCheckORM)).all() == []
