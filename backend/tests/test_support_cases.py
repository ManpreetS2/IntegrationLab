"""Support case lifecycle, evidence, timeline, audit, and correlation tests."""

from __future__ import annotations

from uuid import uuid4

from app.core.correlation import parse_correlation_id
from app.db.models.support import OperatorAuditEventORM


def test_parse_correlation_id_rejects_arbitrary_text():
    assert parse_correlation_id("not-a-uuid") is None
    assert parse_correlation_id("  ") is None
    valid = uuid4()
    assert parse_correlation_id(str(valid)) == valid


def test_create_case_valid_transition_resolve_reopen(client, github_integration_id):
    create = client.post(
        "/api/support-cases",
        json={
            "integration_id": github_integration_id,
            "title": "GitHub authentication failures",
            "severity": "SEV2",
            "impact_summary": "Partner sync failing",
            "suspected_cause": "GitHub authentication failure observed",
        },
    )
    assert create.status_code == 201, create.text
    case = create.json()
    assert case["status"] == "investigating"
    assert case["case_number"].startswith("CASE-")
    assert case["opened_at"]
    case_id = case["id"]

    bad = client.patch(f"/api/support-cases/{case_id}", json={"status": "resolved"})
    # investigating → resolved is allowed per our matrix
    assert bad.status_code == 200

    reopened = client.patch(f"/api/support-cases/{case_id}", json={"status": "reopened"})
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reopened"
    assert reopened.json()["reopened_at"]
    assert reopened.json()["resolved_at"] is None

    identified = client.patch(f"/api/support-cases/{case_id}", json={"status": "identified"})
    assert identified.status_code == 200
    assert identified.json()["identified_at"]

    invalid = client.patch(f"/api/support-cases/{case_id}", json={"status": "reopened"})
    assert invalid.status_code == 400


def test_invalid_transition_from_resolved_to_identified(client, github_integration_id):
    case_id = client.post(
        "/api/support-cases",
        json={"integration_id": github_integration_id, "title": "Transition check", "severity": "SEV4"},
    ).json()["id"]
    assert client.patch(f"/api/support-cases/{case_id}", json={"status": "resolved"}).status_code == 200
    response = client.patch(f"/api/support-cases/{case_id}", json={"status": "identified"})
    assert response.status_code == 400
    assert "Invalid status transition" in response.json()["detail"]


def test_create_case_from_failure_lab_pins_simulated_evidence(client, github_integration_id):
    run = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "rate_limited_429"},
    )
    assert run.status_code == 200, run.text
    run_body = run.json()
    run_id = run_body["id"]

    created = client.post(
        "/api/support-cases",
        json={
            "integration_id": github_integration_id,
            "title": "Rate limit investigation",
            "severity": "SEV3",
            "source_evidence_type": "failure_lab_run",
            "source_evidence_id": run_id,
            "suspected_cause": "GitHub rate limiting observed in Failure Lab",
        },
        headers={"X-Correlation-ID": str(uuid4())},
    )
    assert created.status_code == 201, created.text
    detail = created.json()
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["is_simulated"] is True
    assert "[SIMULATED]" in detail["evidence"][0]["safe_label"]

    timeline = client.get(f"/api/support-cases/{detail['id']}/timeline")
    assert timeline.status_code == 200
    types = {item["type"] for item in timeline.json()}
    assert "case_opened" in types
    assert "evidence_pinned" in types
    assert any(item["is_simulated"] for item in timeline.json())


def test_note_and_severity_change_appear_in_timeline_and_audit(client, github_integration_id):
    case_id = client.post(
        "/api/support-cases",
        json={"integration_id": github_integration_id, "title": "Note test", "severity": "SEV3"},
    ).json()["id"]

    note = client.post(
        f"/api/support-cases/{case_id}/notes",
        json={"body": "Customer reports failures began after credential rotation."},
    )
    assert note.status_code == 201

    severity = client.patch(f"/api/support-cases/{case_id}", json={"severity": "SEV2"})
    assert severity.status_code == 200
    assert severity.json()["severity"] == "SEV2"

    timeline = client.get(f"/api/support-cases/{case_id}/timeline").json()
    assert any(item["type"] == "note" for item in timeline)
    assert any(item["type"] == "severity_changed" for item in timeline)

    audit = client.get("/api/audit-events", params={"support_case_id": case_id})
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()}
    assert "support_case_created" in actions
    assert "support_case_note_added" in actions
    assert "support_case_severity_changed" in actions
    blob = str(audit.json()).lower()
    assert "bearer " not in blob
    assert "whsec_" not in blob
    assert "password" not in blob
    assert "authorization:" not in blob
    for row in audit.json():
        assert row.get("metadata") is None or "secret" not in str(row["metadata"]).lower()


def test_cross_integration_evidence_rejected(client, github_integration_id, stripe_integration_id):
    run = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "rate_limited_429"},
    ).json()
    case_id = client.post(
        "/api/support-cases",
        json={"integration_id": str(stripe_integration_id), "title": "Wrong integration", "severity": "SEV4"},
    ).json()["id"]
    pin = client.post(
        f"/api/support-cases/{case_id}/evidence",
        json={"evidence_type": "failure_lab_run", "evidence_id": run["id"]},
    )
    assert pin.status_code == 400


def test_get_does_not_create_audit_spam(client, github_integration_id, db_session):
    before = db_session.query(OperatorAuditEventORM).count()
    client.get("/api/support-cases")
    client.get("/api/integrations")
    client.get("/api/audit-events")
    after = db_session.query(OperatorAuditEventORM).count()
    assert after == before


def test_correlation_flows_through_failure_lab_and_case(client, github_integration_id):
    correlation = str(uuid4())
    run = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "unauthorized_401"},
        headers={"X-Correlation-ID": correlation},
    )
    assert run.status_code == 200
    run_id = run.json()["id"]

    case = client.post(
        "/api/support-cases",
        json={
            "integration_id": github_integration_id,
            "title": "401 investigation",
            "severity": "SEV2",
            "source_evidence_type": "failure_lab_run",
            "source_evidence_id": run_id,
        },
        headers={"X-Correlation-ID": correlation},
    ).json()
    assert case["correlation_id"] == correlation

    audit = client.get("/api/audit-events", params={"correlation_id": correlation}).json()
    assert len(audit) >= 2
    assert all(row["correlation_id"] == correlation for row in audit)


def test_integration_metadata_defaults_and_patch(client):
    created = client.post(
        "/api/integrations",
        json={"name": "Meta GitHub", "provider": "github"},
    ).json()
    assert created["environment"] == "local"
    assert created["owner_team"] is None

    patched = client.patch(
        f"/api/integrations/{created['id']}",
        json={
            "environment": "staging",
            "owner_team": "demo-ops",
            "criticality": "high",
            "support_tier": "tier2",
            "runbook_url": "https://example.com/runbook",
            "escalation_contact": "oncall-demo",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["environment"] == "staging"
    assert body["owner_team"] == "demo-ops"
    assert body["criticality"] == "high"

    listed = client.get("/api/integrations").json()
    match = next(item for item in listed if item["id"] == created["id"])
    assert match["environment"] == "staging"


def test_seeded_integrations_still_load_with_environment(client):
    rows = client.get("/api/integrations").json()
    assert rows
    assert all("environment" in row for row in rows)
    assert all(row["environment"] in {"local", "test", "staging", "production"} for row in rows)
