"""Unit tests for deterministic FailureDiagnosisEngine."""

from app.services.failure_diagnostics import FailureDiagnosisEngine
from app.services.github_client import ProviderHttpResult


engine = FailureDiagnosisEngine()


def test_diagnose_401_auth_failure() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=401,
        latency_ms=80,
        data=None,
        error_code="github_unauthorized",
        rate_limit_remaining=4999,
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "authentication_failure"
    assert diagnosis.retryable is False
    assert any("401" in item for item in diagnosis.evidence)


def test_diagnose_403_with_quota_is_permission() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=403,
        latency_ms=90,
        data=None,
        error_code="github_forbidden",
        rate_limit_remaining=100,
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "permission_or_access_failure"
    assert diagnosis.retryable is False


def test_diagnose_403_remaining_zero_is_rate_limit() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=403,
        latency_ms=90,
        data=None,
        error_code="github_rate_limited",
        rate_limit_remaining=0,
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "rate_limit_exhausted"
    assert diagnosis.retryable is True


def test_diagnose_404() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=404,
        latency_ms=70,
        data=None,
        error_code="github_not_found",
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "resource_not_found"
    assert diagnosis.retryable is False


def test_diagnose_429() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=429,
        latency_ms=60,
        data=None,
        error_code="github_rate_limited",
        rate_limit_remaining=0,
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "rate_limit_exhausted"
    assert diagnosis.retryable is True


def test_diagnose_500() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=500,
        latency_ms=100,
        data=None,
        error_code="github_server_error",
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "provider_server_failure"
    assert diagnosis.retryable is True


def test_diagnose_timeout() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=None,
        latency_ms=15000,
        data=None,
        error_code="github_timeout",
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "provider_timeout"
    assert diagnosis.retryable is True


def test_diagnose_malformed_json() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=200,
        latency_ms=50,
        data=None,
        error_code="github_malformed_json",
        malformed_body=True,
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "invalid_provider_payload"
    assert diagnosis.retryable is False


def test_diagnose_transport() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=None,
        latency_ms=10,
        data=None,
        error_code="github_transport_error",
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "network_transport_failure"
    assert diagnosis.retryable is True


def test_diagnose_unknown() -> None:
    result = ProviderHttpResult(
        ok=False,
        status_code=418,
        latency_ms=10,
        data=None,
        error_code="github_client_error",
    )
    diagnosis = engine.diagnose(result)
    assert diagnosis.code == "unknown_provider_failure"
