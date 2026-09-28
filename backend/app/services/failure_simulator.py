"""Controlled provider failure simulator (no real network calls)."""

from __future__ import annotations

from app.models.failure_lab import FailureScenario
from app.services.github_client import ProviderHttpResult, classify_github_error


class ProviderFailureSimulator:
    """Produce deterministic ProviderHttpResult values for Failure Lab scenarios.

    Never contacts GitHub. Never uses real credentials.
    Latency values are simulated (not wall-clock sleeps).
    """

    METHOD = "GET"
    ENDPOINT = "/user"
    PROVIDER = "github"

    def simulate(self, scenario: FailureScenario) -> ProviderHttpResult:
        if scenario == FailureScenario.UNAUTHORIZED_401:
            return ProviderHttpResult(
                ok=False,
                status_code=401,
                latency_ms=87,
                data=None,
                error_code=classify_github_error(401),
                rate_limit_remaining=4999,
                headers={"x-ratelimit-remaining": "4999"},
            )

        if scenario == FailureScenario.FORBIDDEN_403:
            return ProviderHttpResult(
                ok=False,
                status_code=403,
                latency_ms=92,
                data=None,
                error_code=classify_github_error(403, rate_limit_remaining=4200),
                rate_limit_remaining=4200,
                headers={"x-ratelimit-remaining": "4200"},
            )

        if scenario == FailureScenario.NOT_FOUND_404:
            return ProviderHttpResult(
                ok=False,
                status_code=404,
                latency_ms=71,
                data=None,
                error_code=classify_github_error(404),
                rate_limit_remaining=4980,
                headers={"x-ratelimit-remaining": "4980"},
            )

        if scenario == FailureScenario.RATE_LIMITED_429:
            return ProviderHttpResult(
                ok=False,
                status_code=429,
                latency_ms=64,
                data=None,
                error_code=classify_github_error(429, rate_limit_remaining=0),
                rate_limit_remaining=0,
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": "1700000000",
                },
            )

        if scenario == FailureScenario.PROVIDER_500:
            return ProviderHttpResult(
                ok=False,
                status_code=500,
                latency_ms=110,
                data=None,
                error_code=classify_github_error(500),
                rate_limit_remaining=4975,
                headers={"x-ratelimit-remaining": "4975"},
            )

        if scenario == FailureScenario.TIMEOUT:
            return ProviderHttpResult(
                ok=False,
                status_code=None,
                latency_ms=15000,
                data=None,
                error_code=classify_github_error(None, timed_out=True),
                rate_limit_remaining=None,
                headers=None,
            )

        if scenario == FailureScenario.MALFORMED_JSON:
            return ProviderHttpResult(
                ok=False,
                status_code=200,
                latency_ms=55,
                data=None,
                error_code=classify_github_error(200, malformed_body=True),
                rate_limit_remaining=4960,
                headers={
                    "content-type": "application/json",
                    "x-ratelimit-remaining": "4960",
                },
                malformed_body=True,
            )

        if scenario == FailureScenario.TRANSPORT_ERROR:
            return ProviderHttpResult(
                ok=False,
                status_code=None,
                latency_ms=12,
                data=None,
                error_code=classify_github_error(None),
                rate_limit_remaining=None,
                headers=None,
            )

        # Exhaustiveness guard for future enum values.
        raise ValueError(f"Unsupported Failure Lab scenario: {scenario}")


provider_failure_simulator = ProviderFailureSimulator()
