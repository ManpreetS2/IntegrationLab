"""Simulator unit tests — no network, deterministic outcomes."""

from app.models.failure_lab import FailureScenario
from app.services.failure_simulator import ProviderFailureSimulator


simulator = ProviderFailureSimulator()


def test_simulate_unauthorized() -> None:
    result = simulator.simulate(FailureScenario.UNAUTHORIZED_401)
    assert result.status_code == 401
    assert result.error_code == "github_unauthorized"
    assert result.ok is False


def test_simulate_forbidden_not_rate_limited() -> None:
    result = simulator.simulate(FailureScenario.FORBIDDEN_403)
    assert result.status_code == 403
    assert result.error_code == "github_forbidden"
    assert result.rate_limit_remaining is not None
    assert result.rate_limit_remaining > 0


def test_simulate_not_found() -> None:
    result = simulator.simulate(FailureScenario.NOT_FOUND_404)
    assert result.status_code == 404
    assert result.error_code == "github_not_found"


def test_simulate_rate_limited() -> None:
    result = simulator.simulate(FailureScenario.RATE_LIMITED_429)
    assert result.status_code == 429
    assert result.error_code == "github_rate_limited"
    assert result.rate_limit_remaining == 0


def test_simulate_provider_500() -> None:
    result = simulator.simulate(FailureScenario.PROVIDER_500)
    assert result.status_code == 500
    assert result.error_code == "github_server_error"


def test_simulate_timeout() -> None:
    result = simulator.simulate(FailureScenario.TIMEOUT)
    assert result.status_code is None
    assert result.error_code == "github_timeout"
    assert result.latency_ms == 15000


def test_simulate_malformed_json() -> None:
    result = simulator.simulate(FailureScenario.MALFORMED_JSON)
    assert result.status_code == 200
    assert result.ok is False
    assert result.error_code == "github_malformed_json"
    assert result.malformed_body is True


def test_simulate_transport() -> None:
    result = simulator.simulate(FailureScenario.TRANSPORT_ERROR)
    assert result.status_code is None
    assert result.error_code == "github_transport_error"
