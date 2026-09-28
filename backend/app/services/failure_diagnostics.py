"""Deterministic Failure Lab diagnosis from observed provider evidence.

Does NOT read the requested scenario name. Classification comes from
status / error_code / rate-limit / malformed flags only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.github_client import ProviderHttpResult


@dataclass(frozen=True)
class Diagnosis:
    code: str
    title: str
    summary: str
    retryable: bool
    evidence: list[str] = field(default_factory=list)
    recommended_checks: list[str] = field(default_factory=list)
    confidence_basis: str = "deterministic_rules"


class FailureDiagnosisEngine:
    """Pure-ish rules engine: observed ProviderHttpResult → diagnosis."""

    def diagnose(self, result: ProviderHttpResult) -> Diagnosis:
        error = result.error_code
        status = result.status_code
        remaining = result.rate_limit_remaining

        evidence = self._build_evidence(result)

        # Prefer normalized error codes first (covers timeout/transport/malformed/oauth).
        if error == "github_timeout" or (status is None and error == "github_timeout"):
            return Diagnosis(
                code="provider_timeout",
                title="Provider timeout",
                summary=(
                    "Evidence indicates the request timed out before a usable HTTP "
                    "response arrived. This may be transient."
                ),
                retryable=True,
                evidence=evidence,
                recommended_checks=[
                    "Provider availability / status page",
                    "Network path between IntegrationLab and the provider",
                    "Configured request timeout",
                    "Whether the timeout is intermittent",
                ],
            )

        if error == "github_transport_error" or (status is None and error == "github_transport_error"):
            return Diagnosis(
                code="network_transport_failure",
                title="Network / transport failure",
                summary=(
                    "Evidence indicates no usable HTTP response was received "
                    "(connection refused/reset/similar). Often transient."
                ),
                retryable=True,
                evidence=evidence,
                recommended_checks=[
                    "DNS / connectivity to the provider",
                    "Proxy or firewall interference",
                    "Provider outage",
                    "Whether the failure is intermittent",
                ],
            )

        if error == "github_malformed_json" or result.malformed_body:
            return Diagnosis(
                code="invalid_provider_payload",
                title="Invalid provider payload",
                summary=(
                    "Evidence indicates the HTTP response could not be parsed as "
                    "expected JSON. HTTP success does not guarantee a usable payload."
                ),
                retryable=False,
                evidence=evidence,
                recommended_checks=[
                    "Response Content-Type",
                    "Provider response format / schema changes",
                    "Proxy or gateway rewriting the body",
                    "Unexpected HTML or error pages returned as JSON",
                ],
            )

        if error == "github_oauth_error":
            return Diagnosis(
                code="oauth_application_error",
                title="OAuth application-level error",
                summary=(
                    "Evidence indicates the token endpoint returned an OAuth error "
                    "payload even though the HTTP status may be 200."
                ),
                retryable=False,
                evidence=evidence,
                recommended_checks=[
                    "Authorization code validity / reuse",
                    "redirect_uri exact match",
                    "PKCE verifier correctness",
                    "OAuth App client credentials configuration",
                ],
            )

        if status == 401 or error == "github_unauthorized":
            return Diagnosis(
                code="authentication_failure",
                title="Authentication failure",
                summary=(
                    "Evidence indicates an authentication failure. Possible causes "
                    "include revoked, expired, malformed, or wrong credentials — "
                    "not a single root cause."
                ),
                retryable=False,
                evidence=evidence,
                recommended_checks=[
                    "Authorization header present and well-formed?",
                    "Token revoked or expired?",
                    "Token belongs to the expected GitHub account?",
                    "Reconnect the provider if the credential is invalid",
                ],
            )

        # Rate limit: explicit 429 OR 403 with remaining=0.
        if status == 429 or error == "github_rate_limited" or (
            status == 403 and remaining == 0
        ):
            return Diagnosis(
                code="rate_limit_exhausted",
                title="Rate limit exhausted",
                summary=(
                    "Evidence indicates provider rate limiting "
                    "(HTTP 429 and/or remaining quota at zero)."
                ),
                retryable=True,
                evidence=evidence,
                recommended_checks=[
                    "Provider rate-limit response headers",
                    "Remaining quota and reset window",
                    "Request frequency / burst patterns",
                    "Duplicate or unnecessary API calls",
                ],
            )

        if status == 403 or error == "github_forbidden":
            return Diagnosis(
                code="permission_or_access_failure",
                title="Permission or access failure",
                summary=(
                    "Evidence indicates a permission/access failure. A 403 can mean "
                    "missing scopes, org policy, resource ACL, or other access rules — "
                    "not automatically a missing OAuth scope."
                ),
                retryable=False,
                evidence=evidence,
                recommended_checks=[
                    "Granted OAuth scopes vs required access",
                    "Resource / organization permissions",
                    "Account access restrictions",
                    "Endpoint authorization requirements",
                ],
            )

        if status == 404 or error == "github_not_found":
            return Diagnosis(
                code="resource_not_found",
                title="Resource not found",
                summary=(
                    "Evidence indicates a not-found response. Providers may also "
                    "return 404 for unauthorized private resources, so absence is "
                    "not always proven."
                ),
                retryable=False,
                evidence=evidence,
                recommended_checks=[
                    "Endpoint path correctness",
                    "Resource id/name spelling",
                    "Resource deleted or renamed",
                    "Whether the provider hides private resources behind 404",
                ],
            )

        if (status is not None and status >= 500) or error == "github_server_error":
            return Diagnosis(
                code="provider_server_failure",
                title="Provider server failure",
                summary=(
                    "Evidence indicates a provider-side server error. These are often "
                    "transient but should be confirmed against provider status."
                ),
                retryable=True,
                evidence=evidence,
                recommended_checks=[
                    "Provider status / incidents",
                    "Whether other endpoints fail similarly",
                    "Recent error frequency",
                    "Whether the failure is transient",
                ],
            )

        return Diagnosis(
            code="unknown_provider_failure",
            title="Unknown provider failure",
            summary=(
                "Observed evidence did not match a more specific deterministic rule. "
                "Investigate status, error code, and headers before assuming a root cause."
            ),
            retryable=False,
            evidence=evidence,
            recommended_checks=[
                "Raw HTTP status and safe error label",
                "Rate-limit headers if present",
                "Whether the response body parsed as expected JSON",
                "Recent similar failures in request logs",
            ],
        )

    def _build_evidence(self, result: ProviderHttpResult) -> list[str]:
        items: list[str] = []
        if result.status_code is None:
            items.append("No HTTP status code was available.")
        else:
            items.append(f"Provider returned HTTP {result.status_code}.")
        items.append(f"Measured latency: {result.latency_ms}ms.")
        if result.error_code:
            items.append(f"Normalized error code: {result.error_code}.")
        if result.rate_limit_remaining is not None:
            items.append(f"X-RateLimit-Remaining observed as {result.rate_limit_remaining}.")
        if result.malformed_body:
            items.append("Response body could not be parsed as JSON.")
        if result.ok:
            items.append("Normalized result marked ok=true.")
        else:
            items.append("Normalized result marked ok=false.")
        return items


failure_diagnosis_engine = FailureDiagnosisEngine()
