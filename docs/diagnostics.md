# Guided Diagnostics

The dashboard is passive: it summarises evidence that already exists.
Diagnostics are **active**. An operator clicks *Run diagnostics*, and
IntegrationLab runs a fixed, ordered list of provider-specific checks, stores
every result, and shows evidence plus a recommendation for each one.

```text
Operator
  → POST /api/diagnostics/{integration_id}/run
  → DiagnosticsService (404 unknown / 400 unsupported provider / 409 run in progress)
  → diagnostic_runs row inserted as "running" and committed
  → provider checks
       GitHub: config → credential → decrypt → one real GET /user → interpret
       Stripe: config + stored webhook evidence only (no outbound calls)
  → diagnostic_checks rows + overall status + summary (one commit)
  → run returned to the UI and kept in history
```

| Endpoint | Purpose |
|----------|---------|
| `POST /api/diagnostics/{integration_id}/run` | Run all checks now and return the persisted run |
| `GET /api/diagnostics/{integration_id}/runs?limit=20` | History, newest first (limit 1–50), with per-status counts |
| `GET /api/diagnostics/runs/{run_id}` | One run with its ordered checks |

Code: `app/services/diagnostics.py` (orchestration),
`diagnostic_checks.py` (result type and summary), `github_diagnostics.py`,
`stripe_diagnostics.py`, and `app/api/diagnostics.py`.

## What is a diagnostic check?

A check is one narrow, named question with a recorded answer. Examples: "Is
`STRIPE_WEBHOOK_SECRET` configured?" and "Did `GET /user` authenticate?". Each
result stores:

- `check_code` and `title`;
- `status`;
- `required`: whether the check can fail the whole run;
- `evidence`: what was observed, in plain language;
- `recommendation`: what to do next, if anything;
- `latency_ms`, for network checks;
- `observed_at`.

## What makes a check deterministic?

The same inputs always produce the same status and wording. Inputs are the
stored rows, environment configuration, and, for GitHub, the HTTP response.
There is no randomness, no model, and no hidden state. Thresholds come from
`reliability_rules.py`, the same module the dashboard uses, so a diagnostic
and a health card never disagree about what "slow" means.

## Observed evidence vs inferred root cause

Evidence is what was seen: "GET /user returned HTTP 401." A root cause is an
explanation: "the token was revoked". IntegrationLab records evidence and
suggests a next step. It does not claim to know the cause. A 401 could mean
revocation, an expired token, or a deleted OAuth app. "Reconnect GitHub" fixes
all three, while guessing among them could mislead.

## Check statuses

| Status | Meaning |
|--------|---------|
| `pass` | The check observed the expected condition |
| `warning` | Something needs attention but does not block the integration |
| `fail` | The condition is broken |
| `unknown` | The check could not be evaluated, for example it was skipped because a prerequisite failed, or the provider returned no usable signal |

**Overall precedence:**

1. Any required check failed → `fail`.
2. Otherwise, any warning, or any failed non-required check → `warning`.
3. Otherwise, any unknown → `unknown`.
4. Otherwise → `pass`.

The summary names the checks that decided the outcome, for example "1 required
check(s) failed: GitHub OAuth configuration."

## Why diagnostics are read-only where possible

A diagnostic that changes state can hide the problem it was meant to find, or
create a new one. Checks never modify `integrations.status`, credentials,
profiles, or webhook events. The GitHub probe calls
`GitHubClient.get_authenticated_user` directly. It deliberately does **not**
reuse "Check connection", because that flow flips the integration to
`needs_setup` on a 401. The only writes are the diagnostic run and check rows,
plus the request log described next.

Concurrent runs are rejected with HTTP 409 while an unfinished run for the same
integration is less than 120 seconds old. After that it is treated as
abandoned. If a check crashes, the run still completes with a single `unknown`
`diagnostic_execution` check, and the server logs only "Diagnostic check failed
for integration <uuid>".

## Why diagnostic API calls are logged

The GitHub probe is a real provider request, so it goes to
`provider_request_logs` with `is_simulated = false` like any other real call.
That keeps the request history honest: it shows every request we actually made.
It also means a diagnostic run produces fresh evidence for the dashboard. A
connected-but-`unknown` GitHub integration becomes `healthy` or `degraded` after
one run.

## How GitHub diagnostics work

Checks run in this order; *required* checks can fail the run.

| # | Check | Required | Outcome |
|---|-------|----------|---------|
| 1 | OAuth configuration | yes | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_OAUTH_REDIRECT_URI`, and `TOKEN_ENCRYPTION_KEY` are present. Missing variables are named; values are never shown. |
| 2 | Connection state | no | `connected` → pass; otherwise warning |
| 3 | Stored credential | yes | An encrypted credential row exists |
| 4 | Token decryption | yes | The Fernet key can decrypt it. The evidence says only whether it worked. |
| 5 | API reachability | yes | No response (timeout or transport) → fail; 5xx → warning |
| 6 | Authentication | yes | 2xx → pass; 401 → fail; 403 that is not a rate limit → fail; rate-limited or 5xx → unknown |
| 7 | Authenticated identity | no | GitHub user id and login from the response |
| 8 | Granted scopes | no | Stored scopes, then the `X-OAuth-Scopes` header. A missing `read:user` is a warning, noting that `/user` still succeeded. |
| 9 | Rate limit | no | Remaining below 100 → warning, with the reset time; no header → unknown |
| 10 | Request latency | no | Above 1500 ms → warning; from 500 ms → pass with an "elevated" note |

If there is no credential or decryption fails, checks 5–10 are recorded as
`unknown`, "Skipped: …", and **no HTTP request is made**. The decrypted token
exists only as a local variable during the single request and is deleted
afterwards.

## How Stripe diagnostics work without a Stripe API key

IntegrationLab has no `STRIPE_SECRET_KEY`, on purpose: it never writes to
Stripe. The inbound side can still be diagnosed completely from what we
store, because every signature-verified delivery, processing attempt, and retry
is already in PostgreSQL.

| Check | Required | Rule |
|-------|----------|------|
| Webhook verification secret | yes | `STRIPE_WEBHOOK_SECRET` is set; otherwise fail (deliveries get 503) |
| Verified webhook receipts | yes | At least one verified event is stored; otherwise unknown |
| Duplicate deliveries | no | Always pass; reports how many redeliveries were absorbed |
| Processing backlog | no | Warning on stale pending events (over 15 min) or scheduled retries |
| Failed queue | no | Fail if events are in the failed queue. Not required, so the run is `warning`: one stuck event does not break receipt. |
| Stale processing | no | Warning if any event has been processing for more than 5 min |
| Recent processing outcomes | no | Unknown with no attempts; warning if every recent attempt failed |
| Retry activity | no | Warning at 5 or more retries in the window |

What this cannot confirm: that the endpoint is registered in the Stripe
dashboard, and that the configured secret belongs to that endpoint. A wrong
secret shows up as rejected deliveries (400s in `stripe listen`) and no new
stored events.

## Why secrets are masked

Diagnostic results are persisted and shown in a browser, and a pasted
screenshot outlives the session. Evidence therefore says *whether* something is
present, never *what* it is. These are never returned, stored, or logged:

- `DATABASE_URL`
- `STRIPE_WEBHOOK_SECRET`
- `GITHUB_CLIENT_SECRET`
- `TOKEN_ENCRYPTION_KEY`
- access tokens, both plaintext and ciphertext
- the PKCE verifier
- the `Stripe-Signature` header
- raw webhook payloads
- `Authorization` headers
- raw provider response bodies

Tests serialise diagnostic and reliability responses and search them, and the
stored check rows, for each of these values.

## Why no AI yet

Deterministic checks are testable, repeatable, and cheap, and their wording can
be reviewed ahead of time. An LLM would add latency, cost, and a new place for
sensitive evidence to go, and it can state a plausible but wrong root cause
with confidence. Once the evidence model is trustworthy, an assistant could
summarise *persisted* runs. It should explain the evidence, not replace it.

## Example walkthrough

GitHub is connected, but the token was revoked in GitHub settings.

1. The dashboard shows GitHub as **unknown**: "Connected, but there is no
   recent real GitHub request evidence." The next step suggests running
   diagnostics.
2. The operator opens **Diagnostics**, selects GitHub, and clicks *Run
   diagnostics*. The button shows "Running diagnostics…".
3. Results:
   - OAuth configuration: pass.
   - Connection state: pass.
   - Stored credential: pass.
   - Token decryption: pass.
   - API reachability: pass. "GitHub responded with HTTP 401 in 212ms."
   - **Authentication: fail.** "GET /user returned HTTP 401."
     Recommendation: "Reconnect GitHub."
   - Identity: unknown. "Skipped: authentication was not confirmed."
   - Scopes, rate limit, and latency are reported from what was observed.
4. Overall: **fail**. "1 required check(s) failed: GitHub authentication."
5. The probe was logged as a real request, so the Overview now shows GitHub
   **failed** with "Latest real GitHub request was rejected as unauthorized
   (HTTP 401)". The Failures page lists both the request and the failed
   diagnostic run.
6. `integrations.status` is still `connected`. The diagnostic observed the
   problem without changing state. Reconnecting GitHub and re-running
   diagnostics gives an overall **pass**.
