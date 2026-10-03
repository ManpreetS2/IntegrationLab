"""Support case lifecycle, evidence, timeline, audit, and correlation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.core.correlation import parse_correlation_id
from app.db.models.oauth import ProviderRequestLogORM
from app.db.models.support import OperatorAuditEventORM
from app.repositories.support import support_case_repository
from tests.stripe_helpers import make_event, post_event


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
    assert case["acknowledged_at"] == case["opened_at"]
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
    assert "failure_lab_run" in types
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


def test_source_evidence_pair_validation(client, github_integration_id):
    only_type = client.post(
        "/api/support-cases",
        json={
            "integration_id": github_integration_id,
            "title": "Missing id",
            "severity": "SEV4",
            "source_evidence_type": "failure_lab_run",
        },
    )
    assert only_type.status_code == 422

    only_id = client.post(
        "/api/support-cases",
        json={
            "integration_id": github_integration_id,
            "title": "Missing type",
            "severity": "SEV4",
            "source_evidence_id": str(uuid4()),
        },
    )
    assert only_id.status_code == 422


def test_case_numbers_unique_via_sequence(client, github_integration_id, db_session):
    a = support_case_repository.next_case_number(db_session)
    b = support_case_repository.next_case_number(db_session)
    assert a != b
    assert a.startswith("CASE-") and b.startswith("CASE-")

    numbers = set()
    for index in range(5):
        created = client.post(
            "/api/support-cases",
            json={
                "integration_id": github_integration_id,
                "title": f"Seq case {index}",
                "severity": "SEV4",
            },
        )
        assert created.status_code == 201, created.text
        numbers.add(created.json()["case_number"])
    assert len(numbers) == 5


def test_audit_excludes_freeform_secret_looking_text(client, github_integration_id):
    sentinel = "sk_live_AUDIT_LEAK_SENTINEL_9f3a"
    created = client.post(
        "/api/integrations",
        json={"name": f"Integration {sentinel}", "provider": "github"},
    )
    assert created.status_code == 201, created.text
    integration_id = created.json()["id"]

    case = client.post(
        "/api/support-cases",
        json={
            "integration_id": integration_id,
            "title": f"Case title with {sentinel}",
            "severity": "SEV3",
        },
    )
    assert case.status_code == 201, case.text

    audit = client.get("/api/audit-events", params={"integration_id": integration_id}).json()
    assert audit
    blob = str(audit)
    assert sentinel not in blob
    assert "sk_live_" not in blob
    for row in audit:
        meta = row.get("metadata") or {}
        assert "title" not in meta
        assert "integration_name" not in meta
        assert sentinel not in row["safe_summary"]


def test_integration_create_rolls_back_when_audit_fails(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise SQLAlchemyError("simulated audit failure")

    monkeypatch.setattr("app.api.integrations.audit_service.record", boom)
    before = {row["id"] for row in client.get("/api/integrations").json()}
    response = client.post(
        "/api/integrations",
        json={"name": "Should Roll Back", "provider": "github"},
    )
    assert response.status_code == 503
    after = {row["id"] for row in client.get("/api/integrations").json()}
    assert after == before


def test_failure_lab_rolls_back_when_audit_fails(client, github_integration_id, monkeypatch, db_session):
    from app.db.models.failure_lab import FailureLabRunORM

    def boom(*_args, **_kwargs):
        raise SQLAlchemyError("simulated audit failure")

    monkeypatch.setattr("app.services.failure_lab.audit_service.record", boom)
    before = db_session.query(FailureLabRunORM).count()
    response = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "provider_500"},
    )
    assert response.status_code == 500
    db_session.expire_all()
    after = db_session.query(FailureLabRunORM).count()
    assert after == before


def test_unscoped_provider_request_cannot_be_pinned(client, github_integration_id, db_session):
    orphan = ProviderRequestLogORM(
        id=uuid4(),
        integration_id=None,
        provider="github",
        method="GET",
        endpoint="/orphan",
        status_code=500,
        latency_ms=10,
        timestamp=datetime.now(timezone.utc),
        is_simulated=False,
    )
    db_session.add(orphan)
    db_session.commit()

    case_id = client.post(
        "/api/support-cases",
        json={"integration_id": github_integration_id, "title": "Orphan pin", "severity": "SEV4"},
    ).json()["id"]
    pin = client.post(
        f"/api/support-cases/{case_id}/evidence",
        json={"evidence_type": "provider_request", "evidence_id": str(orphan.id)},
    )
    assert pin.status_code == 400


def test_timeline_distinguishes_occurred_at_from_pinned_at(
    client, github_integration_id, db_session
):
    occurred = datetime.now(timezone.utc) - timedelta(hours=2)
    request_id = uuid4()
    db_session.add(
        ProviderRequestLogORM(
            id=request_id,
            integration_id=UUID(str(github_integration_id)),
            provider="github",
            method="GET",
            endpoint="/user",
            status_code=401,
            latency_ms=12,
            timestamp=occurred,
            is_simulated=False,
        )
    )
    db_session.commit()

    case_id = client.post(
        "/api/support-cases",
        json={"integration_id": github_integration_id, "title": "Timeline semantics", "severity": "SEV2"},
    ).json()["id"]
    pin = client.post(
        f"/api/support-cases/{case_id}/evidence",
        json={"evidence_type": "provider_request", "evidence_id": str(request_id)},
    )
    assert pin.status_code == 201, pin.text
    pinned_at = datetime.fromisoformat(pin.json()["pinned_at"].replace("Z", "+00:00"))

    timeline = client.get(f"/api/support-cases/{case_id}/timeline").json()
    linked = next(item for item in timeline if item["type"] == "provider_request")
    pin_action = next(item for item in timeline if item["type"] == "evidence_pinned")

    linked_occurred = datetime.fromisoformat(linked["occurred_at"].replace("Z", "+00:00"))
    linked_pinned = datetime.fromisoformat(linked["pinned_at"].replace("Z", "+00:00"))
    assert abs((linked_occurred - occurred).total_seconds()) < 2
    assert linked_pinned >= pinned_at - timedelta(seconds=2)
    assert linked_occurred < linked_pinned
    # Sort key for linked evidence is occurred_at, not pin time.
    assert datetime.fromisoformat(linked["timestamp"].replace("Z", "+00:00")) == linked_occurred
    # Operator pin action remains at pin time via history.
    pin_ts = datetime.fromisoformat(pin_action["timestamp"].replace("Z", "+00:00"))
    assert pin_ts >= pinned_at - timedelta(seconds=2)


def _webhook_event_id(client, stripe_integration_id, **kwargs) -> str:
    response = post_event(client, stripe_integration_id, make_event(**kwargs))
    assert response.status_code == 200
    events = client.get("/api/webhooks/stripe/events", params={"limit": 100}).json()
    return next(e["id"] for e in events if e["provider_event_id"] == response.json()["event_id"])


def test_operator_action_audit_coverage(client, github_integration_id, stripe_integration_id):
    correlation = str(uuid4())
    headers = {"X-Correlation-ID": correlation}

    integration = client.post(
        "/api/integrations",
        json={"name": "Audit Coverage GitHub", "provider": "github"},
        headers=headers,
    )
    assert integration.status_code == 201
    new_id = integration.json()["id"]
    assert (
        client.patch(
            f"/api/integrations/{new_id}",
            json={"environment": "test"},
            headers=headers,
        ).status_code
        == 200
    )

    lab = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "unauthorized_401"},
        headers=headers,
    )
    assert lab.status_code == 200

    diag = client.post(f"/api/diagnostics/{stripe_integration_id}/run", headers=headers)
    assert diag.status_code == 200, diag.text

    case = client.post(
        "/api/support-cases",
        json={
            "integration_id": github_integration_id,
            "title": "Coverage case",
            "severity": "SEV3",
            "source_evidence_type": "failure_lab_run",
            "source_evidence_id": lab.json()["id"],
        },
        headers=headers,
    )
    assert case.status_code == 201
    case_id = case.json()["id"]
    evidence_row_id = case.json()["evidence"][0]["id"]

    assert (
        client.post(
            f"/api/support-cases/{case_id}/notes",
            json={"body": "Investigating auth failures."},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.patch(
            f"/api/support-cases/{case_id}",
            json={"status": "identified"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/support-cases/{case_id}/evidence/{evidence_row_id}",
            headers=headers,
        ).status_code
        == 204
    )

    # Successful process
    ok_id = _webhook_event_id(client, stripe_integration_id, event_id="evt_audit_cov")
    assert client.post(f"/api/webhooks/stripe/events/{ok_id}/process", headers=headers).status_code == 200

    # object_id=None produces a permanent failure → retry + dismiss coverage
    failed_id = _webhook_event_id(
        client, stripe_integration_id, event_id="evt_audit_fail", object_id=None
    )
    assert (
        client.post(f"/api/webhooks/stripe/events/{failed_id}/process", headers=headers).json()[
            "processing_status"
        ]
        == "failed"
    )
    assert (
        client.post(f"/api/webhooks/stripe/events/{failed_id}/retry", headers=headers).status_code
        == 200
    )
    assert (
        client.post(f"/api/webhooks/stripe/events/{failed_id}/process", headers=headers).json()[
            "processing_status"
        ]
        == "failed"
    )

    dismiss_id = _webhook_event_id(
        client, stripe_integration_id, event_id="evt_audit_dismiss", object_id=None
    )
    assert (
        client.post(f"/api/webhooks/stripe/events/{dismiss_id}/process", headers=headers).json()[
            "processing_status"
        ]
        == "failed"
    )
    assert (
        client.post(f"/api/webhooks/stripe/events/{dismiss_id}/dismiss", headers=headers).status_code
        == 200
    )

    assert client.post("/api/webhooks/stripe/process-due", headers=headers).status_code == 200

    actions = {row["action"] for row in client.get("/api/audit-events").json()}
    expected = {
        "integration_created",
        "integration_updated",
        "failure_lab_run",
        "diagnostic_started",
        "support_case_created",
        "support_case_note_added",
        "support_case_status_changed",
        "evidence_pinned",
        "evidence_unpinned",
        "webhook_process_requested",
        "webhook_retry_requested",
        "webhook_dismissed",
        "webhook_process_due_requested",
    }
    missing = expected - actions
    assert not missing, f"missing audit actions: {missing}"


def test_webhook_retry_correlation_flows_to_attempt(client, stripe_integration_id, db_session):
    from app.db.models.webhook import WebhookProcessingAttemptORM

    event_id = _webhook_event_id(
        client, stripe_integration_id, event_id="evt_corr_retry", object_id=None
    )
    assert client.post(f"/api/webhooks/stripe/events/{event_id}/process").json()["processing_status"] == "failed"

    correlation = str(uuid4())
    headers = {"X-Correlation-ID": correlation}
    assert client.post(f"/api/webhooks/stripe/events/{event_id}/retry", headers=headers).status_code == 200
    assert (
        client.post(f"/api/webhooks/stripe/events/{event_id}/process", headers=headers).json()[
            "processing_status"
        ]
        == "failed"
    )

    db_session.expire_all()
    attempts = (
        db_session.query(WebhookProcessingAttemptORM)
        .filter(WebhookProcessingAttemptORM.webhook_event_id == event_id)
        .all()
    )
    assert attempts
    assert any(str(a.correlation_id) == correlation for a in attempts if a.correlation_id)

    audit = client.get("/api/audit-events", params={"correlation_id": correlation}).json()
    assert any(row["action"] == "webhook_retry_requested" for row in audit)
    assert any(row["action"] == "webhook_process_requested" for row in audit)
    assert all(row["correlation_id"] == correlation for row in audit)


def test_webhook_process_skips_processor_when_pre_audit_fails(
    client, stripe_integration_id, monkeypatch
):
    event_id = _webhook_event_id(client, stripe_integration_id, event_id="evt_pre_audit_fail")
    called = {"process_now": False, "process_due": False}

    def boom(*_args, **_kwargs):
        raise SQLAlchemyError("simulated audit failure")

    def spy_process_now(*_args, **_kwargs):
        called["process_now"] = True
        raise AssertionError("processor must not run when pre-audit fails")

    def spy_process_due(*_args, **_kwargs):
        called["process_due"] = True
        raise AssertionError("processor must not run when pre-audit fails")

    monkeypatch.setattr("app.api.stripe_webhooks.audit_service.record", boom)
    monkeypatch.setattr("app.api.stripe_webhooks.webhook_event_service.process_now", spy_process_now)
    monkeypatch.setattr("app.api.stripe_webhooks.stripe_webhook_processor.process_due", spy_process_due)

    process = client.post(f"/api/webhooks/stripe/events/{event_id}/process")
    assert process.status_code == 503
    assert called["process_now"] is False

    due = client.post("/api/webhooks/stripe/process-due")
    assert due.status_code == 503
    assert called["process_due"] is False

    # Event remains pending — processor never claimed it.
    detail = client.get(f"/api/webhooks/stripe/events/{event_id}").json()
    assert detail["processing_status"] == "pending"
    assert detail["attempts"] == []


def test_process_due_request_audit_exists_when_zero_due(client):
    correlation = str(uuid4())
    response = client.post(
        "/api/webhooks/stripe/process-due",
        headers={"X-Correlation-ID": correlation},
    )
    assert response.status_code == 200
    assert response.json() == {
        "processed": 0,
        "retry_scheduled": 0,
        "failed": 0,
        "ignored": 0,
        "skipped": 0,
    }
    audit = client.get("/api/audit-events", params={"correlation_id": correlation}).json()
    assert len(audit) == 1
    assert audit[0]["action"] == "webhook_process_due_requested"
    assert audit[0]["correlation_id"] == correlation
    assert audit[0]["metadata"] == {"limit": 25, "provider": "stripe"}
    assert "processed" not in (audit[0]["metadata"] or {})


def test_github_connect_requested_audit_semantics(
    client, github_integration_id, stripe_integration_id, db_session
):
    before = db_session.query(OperatorAuditEventORM).count()
    correlation = str(uuid4())
    response = client.get(
        f"/api/integrations/{github_integration_id}/github/connect",
        headers={"X-Correlation-ID": correlation},
        follow_redirects=False,
    )
    assert response.status_code in {302, 307}
    assert "github.com" in response.headers.get("location", "")

    audit = client.get("/api/audit-events", params={"correlation_id": correlation}).json()
    assert len(audit) == 1
    row = audit[0]
    assert row["action"] == "github_connect_requested"
    assert row["actor_type"] == "browser_handoff"
    assert row["correlation_id"] == correlation
    assert row["integration_id"] == github_integration_id
    assert row["metadata"] == {"provider": "github"}
    blob = str(row).lower()
    for forbidden in (
        "code_verifier",
        "code_challenge",
        "access_token",
        "client_secret",
        "gho_",
        "authorization_code",
    ):
        assert forbidden not in blob

    # Missing integration → no audit row.
    missing = client.get(
        "/api/integrations/00000000-0000-0000-0000-000000000099/github/connect",
        follow_redirects=False,
    )
    assert missing.status_code == 404

    # Wrong provider → rejected, no GitHub connect audit.
    wrong = client.get(
        f"/api/integrations/{stripe_integration_id}/github/connect",
        follow_redirects=False,
    )
    assert wrong.status_code == 400
    db_session.expire_all()
    after_invalid = db_session.query(OperatorAuditEventORM).count()
    assert after_invalid == before + 1

    # Ordinary GET connection metadata does not audit.
    client.get(f"/api/integrations/{github_integration_id}/github")
    db_session.expire_all()
    assert db_session.query(OperatorAuditEventORM).count() == after_invalid
