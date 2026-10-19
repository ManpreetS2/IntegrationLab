"""CLI worker for webhook processing."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.support import OperatorAuditEventORM
from app.scripts import process_webhooks
from tests.stripe_helpers import store_event

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_cli_process_webhooks_writes_audit_and_processes(db_session, stripe_integration_id) -> None:
    store_event(db_session, stripe_integration_id, now=T0)

    assert process_webhooks.main(["--limit", "5"]) == 0

    db_session.expire_all()
    audit = db_session.scalars(
        select(OperatorAuditEventORM).where(
            OperatorAuditEventORM.action == "webhook_process_due_requested"
        )
    ).all()
    assert len(audit) == 1
    assert audit[0].actor_type == "cli"
    assert audit[0].metadata_json is not None
    assert audit[0].metadata_json.get("limit") == 5
