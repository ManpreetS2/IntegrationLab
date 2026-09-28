# Failure Lab

Failure Lab is IntegrationLab's **safe, deterministic** environment for
reproducing common third-party provider failures and classifying them from
**observed evidence**.

It is about:

**reproduction → evidence → classification → diagnosis**

It is **not** automatic retries, workers, or AI root-cause guessing.

## What is Failure Lab?

A sandboxed simulator that generates realistic provider outcomes
(`ProviderHttpResult`) for known scenarios such as 401, 403, 429, timeout, and
malformed JSON — without calling GitHub and without mutating real credentials.

## Why intentionally reproduce errors?

Partner integrations fail in predictable patterns. Practicing those patterns in
a controlled lab builds the same evidence-based troubleshooting skill used in
Solutions Engineering / Support Engineering interviews.

## Why simulation instead of abusing a real provider?

- Deterministic, offline, fast tests
- No accidental rate-limit abuse
- No revoked-token experiments against production GitHub
- Never damages a real connected integration

## Architecture

```text
React Failure Lab
  → POST /api/failure-lab/run
  → FailureLabService
  → ProviderFailureSimulator
  → ProviderHttpResult (same shape as real GitHubClient)
  → provider_request_logs (is_simulated=true)
  → FailureDiagnosisEngine
  → failure_lab_runs
  → JSON result → UI
```

Real path:

```text
GitHubClient → ProviderHttpResult → provider_request_logs (is_simulated=false)
```

Both paths converge on the **same normalized evidence structure**.

## HTTP status vs transport vs application failure

| Kind | Example | Status |
|------|---------|--------|
| HTTP failure | 401 / 403 / 404 / 429 / 500 | Numeric status |
| Transport failure | connection refused | `null` status |
| Timeout | no response in time | `null` status + `github_timeout` |
| Application failure | OAuth token JSON `{"error":...}` with HTTP 200 | Status 200 + `github_oauth_error` |
| Payload failure | HTTP 200 + invalid JSON | Status 200 + `github_malformed_json` |

**HTTP 200 does not always mean the integration succeeded.**

## Scenario matrix

| Scenario | Evidence | Error code | Diagnosis | Retryable | Next checks |
|----------|----------|------------|-----------|-----------|-------------|
| unauthorized_401 | HTTP 401 | github_unauthorized | authentication_failure | No | Token validity, Authorization header, reconnect |
| forbidden_403 | HTTP 403, remaining > 0 | github_forbidden | permission_or_access_failure | No | Scopes, org policy, resource ACL |
| not_found_404 | HTTP 404 | github_not_found | resource_not_found | No | Path/id, deleted resource, hidden private resources |
| rate_limited_429 | HTTP 429, remaining 0 | github_rate_limited | rate_limit_exhausted | Yes later | Headers, reset window, call frequency |
| provider_500 | HTTP 500 | github_server_error | provider_server_failure | Yes later | Provider status, transience |
| timeout | no status, ~15000ms simulated | github_timeout | provider_timeout | Yes later | Availability, network, timeout setting |
| malformed_json | HTTP 200, parse fail | github_malformed_json | invalid_provider_payload | No (default) | Content-Type, schema, proxies |
| transport_error | no status | github_transport_error | network_transport_failure | Yes later | DNS/connectivity, firewall |

## Deterministic diagnosis

The diagnosis engine receives the **observed result**, not the scenario name.

It must not cheat by mapping `scenario=unauthorized_401` → auth failure.
Instead it reads status / error_code / rate-limit / malformed flags.

No AI. No fake confidence percentages. Rules are interview-explainable.

## Evidence vs root cause

Good:

> Evidence indicates an authentication failure. Likely checks include token
> validity and authorization configuration.

Bad:

> Your token definitely expired.

401 can mean revocation, expiry, wrong credential, or malformed Authorization.

403 is not automatically "missing OAuth scope."

404 does not prove the resource is absent (providers may hide private resources).

## Retryable vs permanent

Failure Lab classifies whether a failure is **generally retryable later**.

It does **not** retry. Retries / backoff / DLQ belong to the next milestone.

## Safety

Simulations:

- do not call GitHub
- do not decrypt OAuth credentials
- do not change integration status / profile / credentials

Real connection checks may still mark `needs_setup` on a **real** 401.
Simulated 401s never do.

## API

- `GET /api/failure-lab/scenarios`
- `POST /api/failure-lab/run` `{ integration_id, scenario }`
- `GET /api/failure-lab/runs`
- `GET /api/failure-lab/runs/{id}`

Scenario input is an enum. Clients cannot pass arbitrary URLs, methods, or headers
(Failure Lab is not an SSRF proxy).

## Related docs

- [architecture.md](architecture.md)
- [database.md](database.md)
- [github-oauth.md](github-oauth.md)
