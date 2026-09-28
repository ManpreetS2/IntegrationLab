# Stripe Webhooks — Receipt, Idempotency, and Retry Processing

IntegrationLab receives Stripe webhooks, verifies them with the official Stripe
SDK, stores a safe normalized summary durably, and processes them separately
with bounded, deterministic retries.

- SDK: `stripe==15.6.1` (`stripe.Webhook.construct_event`)
- Endpoint: `POST /webhooks/stripe/{integration_id}`
- Operator API: `/api/webhooks/stripe/*`
- Worker: `python -m app.scripts.process_webhooks [--limit N]`
- Migration: `004_stripe_webhooks`

No money movement, no refunds, and no Stripe API mutations happen anywhere in
this milestone. `STRIPE_SECRET_KEY` is not needed and not used.

---

## Two phases

```text
Phase A — RECEIPT (inside the HTTP request, fast)
  Stripe → POST raw body
         → integration exists? (404) and provider == stripe? (400)
         → STRIPE_WEBHOOK_SECRET configured? (503)
         → Stripe-Signature present? (400)
         → stripe.Webhook.construct_event(raw_bytes, header, secret)   (400 on failure)
         → normalize safe fields
         → INSERT ... ON CONFLICT DO NOTHING   (dedupe by Stripe event id)
         → COMMIT
         → 200 {"received": true, "duplicate": bool, "event_id": "evt_..."}

Phase B — PROCESSING (outside the request: CLI / "Process due" button)
  webhook_events (pending / due retry_scheduled)
         → claim row (FOR UPDATE SKIP LOCKED) + attempt record
         → HandlerRegistry → handler
         → INSERT effect ON CONFLICT DO NOTHING + mark processed (same commit)
         → on failure: retry policy → retry_scheduled (next_attempt_at) or failed
```

Receipt never runs business logic, never sleeps, and never retries inline.

## Public error responses

| Situation | Status | Body |
|-----------|--------|------|
| Unknown integration | 404 | `Integration not found` |
| Integration is not Stripe | 400 | `Integration provider must be stripe` |
| Secret not configured | 503 | `Stripe webhook verification not configured` |
| Missing `Stripe-Signature` | 400 | `Missing Stripe-Signature header` |
| Bad/expired signature | 400 | `Invalid webhook signature` |
| Malformed/non-object JSON, missing id/type | 400 | `Invalid webhook payload` |
| DB unavailable before durable receipt | 500 | `Failed to store webhook` (Stripe will redeliver) |

Responses never echo the secret, the signature header, or the payload.

## Configuration

```bash
# backend/.env — never commit a real value
STRIPE_WEBHOOK_SECRET=whsec_...   # from `stripe listen` or the Dashboard endpoint
```

The app boots without it; only the webhook endpoint returns 503. Tests use the
obviously fake `whsec_test_example`.

## Event types

| Stripe event | Internal effect |
|--------------|-----------------|
| `payment_intent.succeeded` | `payment_success_recorded` |
| `payment_intent.payment_failed` | `payment_failure_recorded` |
| `charge.refunded` | `refund_recorded` |
| anything else | stored, marked `ignored`, still acknowledged 2xx |

Handlers live in `app/services/webhook_handlers.py` and are registered in a
`HandlerRegistry` (no long `if/elif` chain). Adding a type = one function + one
`register(...)` call.

A supported event missing `data.object.id` raises `PermanentWebhookError`
(`webhook_invalid_event_data`). That is a processing failure, not a signature
failure — the delivery was genuine.

## What is stored (and what is not)

Stored per event: Stripe event id, type, `data.object.id`, `api_version`,
`livemode`, `created`, `amount` (or `amount_refunded` for refunds), `currency`,
plus processing state.

Never stored or logged: the raw body, the `Stripe-Signature` header, the
webhook secret, customer objects, emails, payment method / card details,
`client_secret`s.

Inbound webhooks are **not** written to `provider_request_logs`. That table is
for **outbound** calls IntegrationLab makes to providers (GitHub `/user`, token
exchange, Failure Lab simulations). Inbound deliveries live in
`webhook_events`.

## Processing statuses

| Status | Meaning |
|--------|---------|
| `pending` | Received, not attempted yet (or reopened by manual retry) |
| `processing` | Claimed by a worker |
| `processed` | Handler succeeded; effect committed |
| `retry_scheduled` | Retryable failure; `next_attempt_at` set |
| `failed` | Permanent error or retries exhausted → failed queue |
| `ignored` | Unsupported event type |
| `dismissed` | Operator chose to stop processing it |

## Retry policy

`WebhookRetryPolicy` (`app/services/webhook_retry.py`) is pure and deterministic
with an injectable `now`:

| Cycle attempt | Outcome if it fails (retryable) |
|---------------|--------------------------------|
| 1 | retry in 1s |
| 2 | retry in 2s |
| 3 | retry in 4s |
| 4 | failed queue |

`max_attempts = 4` means 1 initial attempt + 3 retries. Permanent errors
(`PermanentWebhookError`) fail after a single attempt. Unexpected exceptions are
classified as `webhook_processing_error` and treated as retryable, so they still
end in the failed queue rather than retrying forever. The request never sleeps:
the decision is persisted as `next_attempt_at`, and the next worker tick picks it
up.

Error codes: `webhook_handler_temporary_failure`, `webhook_invalid_event_data`,
`webhook_processing_error`, `webhook_processing_abandoned`.

## Worker / due processor

```bash
cd backend && source .venv/bin/activate
python -m app.scripts.process_webhooks --limit 25
# Processed: 3
# Retry scheduled: 0
# Failed: 1
# Ignored: 1
```

Or `POST /api/webhooks/stripe/process-due?limit=25` (max 50) — same code path.

- Picks `pending`, `retry_scheduled` with `next_attempt_at <= now`, and stale
  `processing` rows, oldest first, up to the batch limit.
- Each row is claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, and its status
  is re-checked under the lock, so concurrent workers never process the same
  event at the same time. Locked rows are counted as `skipped`.
- **Stale processing recovery:** if a worker dies mid-attempt, the row stays
  `processing`. After 5 minutes it is reclaimed: the open attempt is closed as
  `abandoned` (`webhook_processing_abandoned`) and a new attempt starts — or the
  event fails if its cycle budget is already used up.
- Run it from cron or a shell loop for continuous processing. There is no
  background daemon (no Redis/Celery by design).

## Idempotency — three layers

1. **Delivery dedupe.** Unique `(integration_id, provider, provider_event_id)`.
   Receipt does `INSERT ... ON CONFLICT DO NOTHING`; on conflict it atomically
   runs `delivery_count = delivery_count + 1, last_received_at = now`. Two
   concurrent deliveries of the same event cannot create two rows. Duplicates
   return 200 with `"duplicate": true` — they are normal, not errors.
2. **Status gate.** Only `pending` / due `retry_scheduled` / stale `processing`
   rows are claimable. A redelivery of an already `processed` event does not
   reset its status, so it is not processed again.
3. **Effect-level idempotency.** Unique `(webhook_event_id, effect_key)` where
   `effect_key = "stripe:<event id>:<effect type>"`. The effect insert uses
   `ON CONFLICT DO NOTHING` and commits in the **same transaction** as
   `processed`.

Crash window: if the process dies after the effect commits but before the
status update, the next attempt re-inserts the effect as a no-op and then marks
the event processed. There is a test for exactly this case.

## Failed queue, manual retry, dismiss

- `GET /api/webhooks/stripe/failed` — newest failure first.
- `POST /events/{id}/retry` (failed or dismissed only): sets `pending` due
  now, increments `manual_retry_count` and `retry_cycle`, resets the cycle
  attempt counter (fresh 4-attempt budget), clears `failed_at`/`dismissed_at`.
  All previous attempts stay in `webhook_processing_attempts`; new ones carry
  the new `retry_cycle`.
- `POST /events/{id}/dismiss` (failed or retry_scheduled only): status
  `dismissed`, `dismissed_at` set, history kept. Dismissed events are never
  picked up by the due processor. The UI asks for confirmation.
- `POST /events/{id}/process` processes one pending / retry_scheduled event now
  and returns 409 if it is already processing or not in a processable state.

## Operator API summary

| Method | Path |
|--------|------|
| GET | `/api/webhooks/stripe/summary` |
| GET | `/api/webhooks/stripe/events?status=&event_type=&integration_id=&limit=1..100` |
| GET | `/api/webhooks/stripe/events/{id}` (effects + attempt timeline, no raw data) |
| POST | `/api/webhooks/stripe/events/{id}/process` |
| POST | `/api/webhooks/stripe/process-due?limit=1..50` |
| GET | `/api/webhooks/stripe/failed` |
| POST | `/api/webhooks/stripe/events/{id}/retry` |
| POST | `/api/webhooks/stripe/events/{id}/dismiss` |

These are local/prototype controls: there is no app user authentication yet.

## Local testing

### Automated (no Stripe account needed)

`backend/tests/stripe_helpers.py` builds events and signs them locally with
`stripe.WebhookSignature.generate_signature_header(payload, secret="whsec_test_example")`,
then POSTs the exact bytes. There is **no** fake/bypass endpoint in the API.

```bash
cd backend && pytest tests/test_stripe_webhook_receipt.py tests/test_webhook_processing.py \
  tests/test_webhook_retry_policy.py tests/test_webhook_admin_api.py
```

### With the Stripe CLI (real signed test-mode deliveries)

```bash
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe/<stripe-integration-id>
# copy the printed whsec_... into backend/.env as STRIPE_WEBHOOK_SECRET, restart uvicorn

stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
stripe trigger charge.refunded

python -m app.scripts.process_webhooks
```

`stripe events resend <evt_id>` re-sends one event to demonstrate duplicate
handling (`delivery_count` increases, the effect stays at 1).

**Status in this milestone:** REAL STRIPE CLI WEBHOOK FLOW NOT VERIFIED — the
Stripe CLI is not installed on the development machine. Verification so far
uses locally signed payloads with a fake secret, through the real HTTP
endpoint and the official SDK verifier.

## Known limitations

- One global `STRIPE_WEBHOOK_SECRET` shared by all Stripe integrations; per-integration secrets would need encrypted storage.
- Processing is triggered by the CLI / button, not by a daemon.
- Stale `processing` recovery waits a fixed 5 minutes.
- Effects are internal records only; there's no ledger or order system behind them yet.
- No app authentication on operator endpoints.
- Secret rotation (two active secrets) is not supported yet.

---

# Interview study notes

**What is a webhook?** An HTTP request a provider sends *to you* when something
happens on their side ("payment succeeded"). It's a push, instead of you
polling their API.

**Why do providers use webhooks?** Many outcomes are asynchronous (bank
confirmations, disputes, refunds). Pushing events is cheaper and faster than
millions of clients polling.

**Why do signatures matter?** The endpoint is public. Anyone can POST JSON that
claims "payment succeeded". An HMAC signature computed with a shared secret
proves the payload came from Stripe and was not modified.

**Why does the raw body matter?** The signature covers the exact bytes Stripe
sent. Parsing and re-serializing JSON changes whitespace, key order, or number
formatting, and the HMAC no longer matches. FastAPI reads `await request.body()`
and passes those bytes untouched to `construct_event`. A test proves that a
pretty-printed copy of a validly signed body is rejected.

**What is `Stripe-Signature`?** A header like `t=<unix ts>,v1=<hex hmac>`. The
HMAC-SHA256 is over `"{t}.{raw_body}"` using the endpoint secret (`whsec_...`).

**What is webhook replay?** An attacker who captured one valid delivery re-sends
it later. The signature is still valid because the bytes did not change.

**Why does signature timestamp validation matter?** `t` is signed too. The SDK
rejects signatures older than the tolerance (default 300s), which bounds the
replay window. Dedupe by event id handles the rest.

**Why do duplicates happen?** Stripe retries whenever it doesn't see a timely
2xx — timeouts, network blips, deploys — even if you actually processed the
first delivery. Operators can also resend events manually.

**What is idempotency?** Doing an operation once or N times leaves the same
result. Here: N deliveries of `evt_123` → one row, one effect.

**Why is the Stripe event id useful?** It is stable across every redelivery of
the same logical event, so it is the natural dedupe key.

**Why can't event ordering be assumed?** Deliveries are independent HTTP
requests with independent retries. `charge.refunded` can arrive before
`payment_intent.succeeded`. Each handler must be correct on its own; there is a
test for refund-before-success.

**What is at-least-once delivery?** The provider guarantees every event
arrives, possibly more than once. It never promises exactly once.

**Exactly-once vs effectively-once?** True exactly-once delivery over a network
isn't achievable. You get *effectively-once* by combining at-least-once
delivery with idempotent processing: duplicates arrive but have no additional
effect.

**Why effect-level idempotency too?** Event-row dedupe stops duplicate
*deliveries*. But *processing* can be replayed too: a crash after applying the
effect but before marking the event processed, a manual retry, or a stale
reclaim. The unique `(event, effect_key)` constraint makes the side effect
itself impossible to apply twice.

**What is exponential backoff?** Each retry waits longer (1s, 2s, 4s …). It
gives a struggling dependency time to recover instead of hammering it.

**Why 1s/2s/4s?** It is short enough to demo and test deterministically, and it
shows the doubling pattern. Production values would be larger (minutes to
hours) and usually jittered.

**What makes an error retryable?** A temporary condition that might succeed
later: a dependency timeout, a lock conflict, a 503 from a downstream service.

**Why not retry permanent errors?** Invalid data stays invalid. Retrying wastes
work, delays alerting, and can mask bugs. Such events should fail fast and be
visible.

**What is a failed / dead-letter queue?** Where events go when automatic
processing has given up. They keep their full history, a human can
inspect them, and they can be retried (after a fix) or dismissed.

**Stripe delivery retries vs IntegrationLab processing retries?**
- *Stripe delivery retries*: Stripe re-sends when **our endpoint** doesn't
  acknowledge with 2xx. Stripe owns this (it can retry for days).
- *IntegrationLab processing retries*: after we durably stored the event and
  returned 2xx, **our processor** may fail. We own this: attempts, backoff,
  failed queue.
- We never return 5xx to Stripe because of an internal processing failure after
  durable receipt. That would cause pointless redeliveries of an event we
  already have.

**Why return 2xx quickly?** Stripe expects an acknowledgement within seconds.
Slow handlers cause timeouts, which cause redeliveries. Store first, process
later.

**Inbound event ids vs outbound `Idempotency-Key`?**
- *Inbound*: Stripe's `evt_...` id identifies an event **Stripe sends us**. We
  dedupe on it.
- *Outbound*: the `Idempotency-Key` header is something **we send Stripe** on
  mutating API calls (e.g. create refund) so that our retries don't
  double-charge. This milestone makes no mutating Stripe calls, so no
  `Idempotency-Key` is used — but it's the mirror image of the same idea.
