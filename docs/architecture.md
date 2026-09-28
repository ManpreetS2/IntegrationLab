# IntegrationLab Architecture — GitHub OAuth + Observability

IntegrationLab still uses the PostgreSQL foundation from the previous milestone.
This milestone adds the first **real third-party provider connection**: GitHub
OAuth + authenticated REST + provider request logging.

## High-level flow (current)

```text
Browser
  → React (http://localhost:5173)
  → FastAPI (http://localhost:8000)
  → GitHub OAuth / REST API
  → PostgreSQL (credentials, profile, request logs)
```

## Layers

```text
Route
  → GitHubOAuthService
  → GitHubClient (httpx)
  → repositories
  → SQLAlchemy Session
  → PostgreSQL
```

React never talks to GitHub or PostgreSQL directly.

## OAuth start

```text
React (Connect GitHub link)
  → GET /api/integrations/{id}/github/connect
  → validate integration + OAuth config
  → generate state + PKCE (S256)
  → store oauth_sessions (hashed state, encrypted verifier)
  → 302 Redirect → GitHub authorize URL
```

Authorization URL includes: `client_id`, `redirect_uri`, `state`,
`code_challenge`, `code_challenge_method=S256`, `scope=read:user`.

## Callback

```text
GitHub
  → GET /api/oauth/github/callback?code=&state=
  → validate OAuth session (hash, expiry, single-use, provider)
  → decrypt PKCE verifier
  → POST GitHub /login/oauth/access_token
  → GET GitHub /user
  → encrypt access token → oauth_credentials
  → upsert github_profiles
  → mark integration connected
  → mark oauth session used
  → 302 Redirect → FRONTEND_URL/?oauth=github&status=connected
```

Why React never receives the token:

- Token exchange runs only on the backend (needs `client_secret`).
- Access tokens are encrypted and stored in PostgreSQL.
- API responses and frontend redirects intentionally omit tokens and ciphertext.

## Check connection

```text
React (Check connection)
  → POST /api/integrations/{id}/github/check
  → load encrypted credential
  → decrypt token
  → GET GitHub /user
  → write provider_request_logs
  → update profile + last_checked_at + status
  → safe JSON result (no token)
```

- Success → `connected`
- Provider `401` → `needs_setup`

## Provider request logging

Every outbound GitHub HTTP call from `GitHubClient` records:

- provider, method, endpoint
- status_code (nullable on transport failure)
- latency_ms (`time.perf_counter()`)
- timestamp
- sanitized error label
- optional `X-RateLimit-Remaining`

Tradeoff: request-log persistence commits separately from the main OAuth
transaction so a logging failure does not undo a successful provider call.
Credential/profile writes still roll back together if persistence fails after
a successful `/user` fetch during callback.

## Existing Day-1 / Postgres APIs (unchanged)

- `GET /health` — liveness (no GitHub config required)
- `GET /ready` — Postgres readiness
- `GET /api/integrations`
- `POST /api/integrations`

## Intentional non-goals (next: Failure Lab)

- Failure Lab simulators (401/429/500/timeout)
- Retries / backoff / DLQ
- Stripe APIs / webhooks
- Redis / queues / AWS
- Application user authentication

## Related docs

- [github-oauth.md](github-oauth.md) — setup + security + interview notes
- [database.md](database.md) — tables, encryption, ER diagram
