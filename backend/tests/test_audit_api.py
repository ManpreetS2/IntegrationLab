"""Audit API query validation."""


def test_audit_since_rejects_timezone_less_datetime(client) -> None:
    response = client.get("/api/audit-events", params={"since": "2026-10-19T16:00:00"})
    assert response.status_code == 422
    assert "timezone" in response.text.lower()


def test_audit_until_rejects_timezone_less_datetime(client) -> None:
    response = client.get("/api/audit-events", params={"until": "2026-10-19T16:00:00"})
    assert response.status_code == 422


def test_audit_accepts_utc_offset(client) -> None:
    response = client.get(
        "/api/audit-events",
        params={"since": "2026-10-19T16:00:00+00:00"},
    )
    assert response.status_code == 200
