# IntegrationLab Architecture — Failure Lab + GitHub OAuth

IntegrationLab now has two evidence paths that share one normalized result shape.

## High-level

```text
Browser
  → React
  → FastAPI
  → (real GitHubClient | Failure Lab simulator)
  → ProviderHttpResult
  → PostgreSQL (request logs / failure runs / OAuth tables)
```

## Real provider path

```text
React
  → FastAPI (connect / callback / check)
  → GitHubClient (httpx)
  → GitHub
  → ProviderHttpResult
  → provider_request_logs (is_simulated=false)
  → credentials / profile / status updates (real only)
```

## Failure Lab path

```text
React Failure Lab
  → POST /api/failure-lab/run
  → FailureLabService
  → ProviderFailureSimulator (no network)
  → ProviderHttpResult
  → provider_request_logs (is_simulated=true, scenario=...)
  → FailureDiagnosisEngine (evidence → diagnosis)
  → failure_lab_runs
  → JSON result → UI
```

### Why this matters

Both paths converge on `ProviderHttpResult`. Diagnosis and observability reason
about **evidence**, not about which UI button was clicked.

Simulations never mutate real connection health or decrypt tokens.

## Layers

| Layer | Role |
|-------|------|
| Routes (`app/api`) | HTTP |
| Services | OAuth, GitHub client, Failure Lab, diagnosis |
| Repositories | DB access |
| ORM (`app/db/models`) | Tables |
| Pydantic (`app/models`) | API contracts |

## OAuth (unchanged core)

Start → state + PKCE → GitHub → callback → token exchange → `/user` → encrypted
credential + profile → frontend redirect.

Hardening in this milestone:

- OAuth cancel (`error=access_denied`) → safe frontend redirect
- Token endpoint HTTP 200 + `{"error":...}` → `github_oauth_error`
- HTTP 200 + malformed JSON → `github_malformed_json`
- 403 + `X-RateLimit-Remaining: 0` → rate-limit classification

## Intentional non-goals

- Automatic retries / backoff / DLQ
- Stripe webhooks
- Redis / Celery / queues / AWS
- AI diagnosis
- Application user login

## Related docs

- [failure-lab.md](failure-lab.md)
- [github-oauth.md](github-oauth.md)
- [database.md](database.md)
