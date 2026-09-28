# IntegrationLab Architecture — GitHub OAuth, Failure Lab, Stripe Webhooks

IntegrationLab has three flows: outbound calls to providers (real GitHub and
simulated Failure Lab), and inbound provider events (Stripe webhooks).

## High-level

```text
Browser
  → React
  → FastAPI
  → (real GitHubClient | Failure Lab simulator)    outbound
  → ProviderHttpResult
  → PostgreSQL (request logs / failure runs / OAuth tables)

Stripe
  → FastAPI public webhook route                   inbound
  → PostgreSQL (webhook_events / attempts / effects)
```

## Outbound vs inbound observability

| | Outbound | Inbound |
|---|----------|---------|
| Who initiates | IntegrationLab calls the provider | Provider calls IntegrationLab |
| Examples | GitHub token exchange, `/user`, Failure Lab | Stripe webhooks |
| Stored in | `provider_request_logs` | `webhook_events` (+ attempts, effects) |

Inbound webhooks are intentionally **not** written to `provider_request_logs`.

## Real provider path (outbound)

```text
React
  → FastAPI (connect / callback / check)
  → GitHubClient (httpx)
  → GitHub
  → ProviderHttpResult
  → provider_request_logs (is_simulated=false)
  → credentials / profile / status updates (real only)
```

## Failure Lab path (outbound, simulated)

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

Both outbound paths converge on `ProviderHttpResult`, so diagnosis reasons
about evidence rather than about which button was clicked. Simulations never
mutate real connection health or decrypt tokens. Failure Lab data never goes
into the webhook tables.

## Stripe webhook path (inbound)

```text
INBOUND (in the HTTP request)
Stripe
  → POST /webhooks/stripe/{integration_id}  (exact raw body)
  → StripeWebhookReceiver
  → stripe.Webhook.construct_event  (signature + timestamp tolerance)
  → normalize safe fields
  → dedupe (INSERT … ON CONFLICT DO NOTHING / delivery_count + 1)
  → PostgreSQL commit
  → HTTP 200 {"received": true, "duplicate": …}

PROCESSING (outside the request)
webhook_events row
  → StripeWebhookProcessor (CLI or POST /process-due)
  → claim: FOR UPDATE SKIP LOCKED → processing + attempt row
  → HandlerRegistry → event handler
  → webhook_effects (ON CONFLICT DO NOTHING) + processed   (one commit)

RETRY
handler raises RetryableWebhookError
  → attempt row closed as failed
  → WebhookRetryPolicy (1s / 2s / 4s, 4 attempts)
  → retry_scheduled + next_attempt_at
  → next process-due tick
  → success  OR  failed queue (manual retry / dismiss)
```

Stripe's own delivery retries are a separate system:

```text
STRIPE DELIVERY RETRY (owned by Stripe)
Stripe → our endpoint → no 2xx (timeout / 4xx / 5xx) → Stripe re-sends later
```

We return 2xx once the event is durably stored, even if processing will later
fail; internal failures are handled by our own retry engine. See
[stripe-webhooks.md](stripe-webhooks.md).

## Layers

| Layer | Role |
|-------|------|
| Routes (`app/api`) | HTTP (public webhook router + operator router) |
| Services | OAuth, GitHub client, Failure Lab, diagnosis, webhook receiver/processor/handlers/retry policy |
| Repositories | DB access (incl. idempotent inserts, row locking) |
| ORM (`app/db/models`) | Tables |
| Pydantic (`app/models`) | API contracts |
| Scripts (`app/scripts`) | seed, `process_webhooks` worker tick |

## OAuth

Start → state + PKCE → GitHub → callback → token exchange → `/user` → encrypted
credential + profile → frontend redirect.

Cancel/error callbacks are only honoured for a known, unused, unexpired GitHub
state. Valid state + `access_denied` marks the state used and redirects with
`status=cancelled`. Missing, unknown, expired, or reused state → HTTP 400.
`error_description` is never reflected.

## Intentional non-goals

- Redis / Celery / queues / AWS
- Background daemon (the worker runs as a single CLI tick)
- Real payment mutations or Stripe API writes
- AI diagnosis
- Application user login

## Related docs

- [stripe-webhooks.md](stripe-webhooks.md)
- [failure-lab.md](failure-lab.md)
- [github-oauth.md](github-oauth.md)
- [database.md](database.md)
