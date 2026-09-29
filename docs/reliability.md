# Reliability Model

The reliability dashboard answers one question per integration: *based on
stored evidence, is this integration working right now?* It reads only
PostgreSQL. Loading the dashboard never calls GitHub or Stripe.

```text
provider_request_logs (real only) ─┐
webhook_events + attempts ─────────┤
failure_lab_runs (labelled only) ──┼─→ reliability repository (grouped SQL)
diagnostic_runs ───────────────────┘        │
                                            ▼
                               health_evaluator (pure rules)
                                            │
                                            ▼
                      GET /api/reliability/overview → Overview page
```

Code:

| Piece | File |
|-------|------|
| Thresholds and wording | `backend/app/services/reliability_rules.py` |
| Pure rules | `backend/app/services/health_evaluator.py` |
| Aggregate queries | `backend/app/repositories/reliability.py` |
| Assembly, failures feed, metrics | `backend/app/services/reliability.py` |
| Routes | `backend/app/api/reliability.py` |

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/reliability/system` | Database reachability only (`healthy` / `failed`) |
| `GET /api/reliability/overview?window_hours=24` | Totals, per-integration health, 10 most recent failures, operational metrics |
| `GET /api/reliability/integrations/{id}` | One integration's health, plus its recent failures and diagnostic runs (20 each) |
| `GET /api/reliability/failures` | Filters: `provider`, `integration_id`, `source`, `limit` (1–100, default 50), `include_simulated` (default `false`), `window_hours` (default 168) |
| `GET /api/reliability/request-metrics` | Count, errors, error rate, average and p95 latency. Filters: `provider`, `integration_id`, `is_simulated` (omit for real + simulated) |

`window_hours` defaults to 24 (168 for the failures feed) and must be between 1 and 168. Every list is
bounded, and filters use typed enums; no endpoint accepts free-form sort or SQL.

## Health states

| State | Meaning |
|-------|---------|
| `healthy` | Recent evidence exists and every rule passed |
| `degraded` | Evidence shows a partial problem; the integration still works in part |
| `failed` | Evidence shows the integration cannot work until someone acts |
| `unknown` | Configured, but there is not enough recent evidence to judge |
| `not_configured` | Setup is incomplete, so health is not applicable yet |

Overview totals count integrations per state. The UI shows not-configured
integrations as a note instead of mixing them into the health counts.

## GitHub rules (first match wins)

1. `not_connected` → **not_configured**.
2. `needs_setup` (an earlier authenticated request was rejected) → **failed**.
3. Marked connected but no stored credential → **failed**.
4. No real requests in the window → **unknown**, even if older requests exist.
5. The latest real request returned 401 → **failed** (reconnect).
6. The latest real request has another error code (timeout, 5xx, 403, 429,
   malformed JSON…) → **degraded**, with a code-specific next step.
7. At least 3 failures in the window, or an error rate of 25% or more with at
   least 4 samples → **degraded**.
8. The latest latency is above 1500 ms → **degraded**. From 500 ms up it is
   labelled "elevated" but stays healthy.
9. `x-ratelimit-remaining` is below 100 → **degraded**.
10. Otherwise → **healthy**.

Only `is_simulated = false` request logs count.

## Stripe rules (first match wins)

1. `STRIPE_WEBHOOK_SECRET` unset → **not_configured**. New deliveries get
   HTTP 503, and any earlier events are mentioned in the evidence.
2. Zero verified events stored → **unknown**.
3. Any of these → **degraded**, with every problem listed:
   - events in the failed queue;
   - events in `retry_scheduled`;
   - events stuck in `processing` for more than 5 minutes (the processor's
     stale-claim window);
   - events left `pending` for more than 15 minutes.
4. Otherwise → **healthy**. Recent pending events are noted but not penalised.

Duplicate deliveries appear in the evidence but never lower health.

## System health

`GET /api/reliability/system` runs `SELECT 1`. If the database is unreachable,
it returns HTTP 503 with `"database": "failed"`. The data endpoints (overview,
integration detail, failures, request metrics) return
`503 {"message": "Database unavailable", "database": "failed"}`. The header
indicator polls `/system` and shows "Database unavailable".
Integrations are **not** marked failed, because no evidence about them could be
read.

---

## Questions and answers

### What is reliability?

Reliability is the probability that an integration does its job when it is
needed. Examples: a GitHub request succeeds with a valid credential, or a
Stripe event is verified, stored, and processed exactly once. You cannot
measure a probability directly. You estimate it from evidence such as request
outcomes, latency, and queue state.

### What is observability?

Observability is how well you can explain a system's internal state from the
signals it emits. IntegrationLab's signals are request logs, webhook events,
processing attempts, and diagnostic check results. The dashboard is only as
good as those signals. If something is not logged, the dashboard cannot know
about it and must say so.

### Health, status, configuration, availability

| Concept | Question it answers | Source |
|---------|---------------------|--------|
| **Status** | What lifecycle state is this record in? | `integrations.status` (`not_connected`, `connected`, `needs_setup`) |
| **Configuration** | Is everything needed to operate present? | Environment variables, stored credential, webhook secret |
| **Availability** | Can the provider be reached right now? | Transport and HTTP outcome of a real request |
| **Health** | Given recent evidence, is it working? | The evaluator's rules applied to all of the above |

### Why connection status ≠ health

`connected` only records that OAuth once succeeded. The token can be revoked,
GitHub can time out, and the quota can run out, all while the status still says
`connected`. Health is derived from recent real outcomes, so a connected
integration can be `unknown`, `degraded`, or `failed`. The evaluator never
writes back to `integrations.status`.

### Why missing evidence produces `unknown`

"No errors observed" is not the same as "working". If nothing called GitHub
in the last 24 hours, the credential could have been revoked an hour ago.
Reporting `healthy` would be a guess. `unknown` states the truth and suggests
the fix: run diagnostics to collect evidence.

### Why simulations must not affect live health

Failure Lab deliberately produces 401s, 429s, and timeouts. If those counted,
every experiment would page someone for an outage that never happened. The
evaluator reads only `is_simulated = false`. The failures feed hides Failure
Lab runs unless `include_simulated=true`, and even then labels them
"Simulation".

### What is error rate?

Error rate is failed requests divided by total requests in the window. A request
fails if it has an error code or a non-2xx status. The Requests page shows it
as "x / n" rather than only as a percentage, so the sample size is always
visible.

### What is p95 latency?

p95 is the latency that 95% of requests were at or below. It shows the tail
that averages hide: nine 100 ms requests and one 3000 ms request average
390 ms, which looks fine, while the slow request is what users feel.
IntegrationLab computes nearest-rank p95 in SQL with `percentile_disc(0.95)`.

### Why sample size matters

One failure out of one request is a 100% error rate, but that is weak evidence.
The error-rate rule therefore needs at least 4 samples. Below that, only the
latest outcome and the repeated-failure count (3 or more) apply. The UI shows
raw counts next to every rate.

### Why separate evidence from conclusions

Each integration card shows the conclusion (health plus a one-line summary),
the evidence lines that produced it, and a recommended next step. An operator
can disagree with a rule, but not with "3 / 12 real requests failed in the last
24h". Keeping them separate makes the dashboard auditable and lets thresholds
change without hiding the data.

### Why deterministic rules

The same evidence always gives the same state and the same explanation. That
makes the rules testable as pure functions without a database or clock,
explainable in a sentence, and safe to review. All thresholds live in one module
and are labelled as local thresholds, not provider SLAs.

### How GitHub and Stripe health differ

GitHub is **outbound**: IntegrationLab calls it, so health comes from the
outcomes, latency, and quota of our own requests. Stripe is **inbound**: Stripe
calls us, so health comes from our side of the contract. That means
verification is configured, events arrive and are stored, and our processor
drains them. A quiet GitHub integration is `unknown`. A Stripe integration with
old processed events and no new deliveries is still healthy, because inbound
volume depends on Stripe traffic, not on us.

### Why Stripe duplicates are not automatically errors

Stripe delivers at least once, so redeliveries are expected, for example after
a slow 2xx or a network blip. Receipt dedupes on `(integration, provider,
event_id)` and effects are idempotent, so a duplicate is proof the safeguards
are working. Duplicates are counted and shown, never penalised.

### Why failed processing means degraded, not failed

A failed webhook event means one event's handler could not finish. Signature
verification, receipt, and processing of other events can still work. The
integration is partly working, and the failed queue gives the operator a
recovery path (retry or dismiss). `failed` is reserved for "nothing can work
until someone acts".

### Why a database failure must not mark every provider failed

If PostgreSQL is down, the dashboard cannot read any evidence. GitHub and
Stripe may be perfectly fine. Showing every integration as failed would blame
the providers for our own outage and send the operator to the wrong place. The
API returns one clear 503, "Database unavailable", and the UI shows that
instead of stale or invented integration states.

## Not implemented

- Uptime percentages, SLAs, or incident counts. There is no continuous sampling
  that could support them.
- Background monitoring or alerts. Health is computed only when someone asks.
- A data retention policy. Evidence tables grow until pruned manually.
