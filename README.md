# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting,
monitoring, debugging, and recovering third-party API integrations.

## Current milestone: Reliability Dashboard + Guided Diagnostics

Working pieces:

- React + TypeScript operator console, with hash-routed pages: Overview,
  Integrations, Requests, Webhooks, Failures, Diagnostics
- FastAPI + PostgreSQL + SQLAlchemy + Alembic
- GitHub OAuth (state + PKCE + encrypted tokens)
- Provider request logging (outbound)
- Failure Lab: a sandboxed scenario simulator with deterministic diagnosis
- Stripe webhooks:
  - signature verification on the exact raw body;
  - durable receipt;
  - dedupe and idempotent effects;
  - 1s/2s/4s retries;
  - a failed queue with manual retry and dismiss.
- **Reliability dashboard**:
  - Deterministic health per integration: `healthy`, `degraded`, `failed`,
    `unknown`, or `not_configured`.
  - Health is derived only from real stored evidence.
  - Separate database health.
  - A unified recent-failures feed; simulations are opt-in and labelled.
  - Request metrics: error rate and p95 latency.
- **Guided diagnostics**:
  - Operator-triggered GitHub and Stripe checks, each with evidence and a
    recommendation.
  - Results are persisted as runs with ordered checks and a history.

## Architecture

Reliability (passive; reads PostgreSQL only):

```text
Evidence sources
  GitHub request logs (real)
  Stripe webhook processing
  Failure Lab (labelled, excluded from health)
  Diagnostic runs
    → Reliability evaluator (deterministic rules)
    → Overview
```

Active diagnostics:

```text
Operator → Run diagnostics → provider-specific checks → evidence
         → recommendations → persisted run
```

Loading the dashboard never calls a provider. Only an explicit diagnostic run
does: a single real GitHub `GET /user`, logged as a real request. Stripe
diagnostics use stored webhook evidence and need no Stripe API key.

Outbound (real):

```text
GitHub → ProviderHttpResult → request log (real)
```

Outbound (Failure Lab):

```text
Simulator → ProviderHttpResult → request log (simulated) → diagnosis → failure run
```

Inbound (Stripe):

```text
Stripe → raw body → signature check → dedupe → webhook_events → 200
webhook_events → processor → handler → effect (once) → processed
                                  └─ retryable failure → 1s/2s/4s → failed queue
```

Simulated failures **do not** affect real provider connection state. Inbound
webhooks are stored in `webhook_events`, not in the outbound request log.

See:

- [docs/reliability.md](docs/reliability.md)
- [docs/diagnostics.md](docs/diagnostics.md)
- [docs/stripe-webhooks.md](docs/stripe-webhooks.md)
- [docs/failure-lab.md](docs/failure-lab.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/database.md](docs/database.md)
- [docs/github-oauth.md](docs/github-oauth.md)

## Quick start

```bash
# DB
docker compose up -d postgres   # or local Postgres matching DATABASE_URL

cp .env.example backend/.env
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

### Stripe webhooks locally

Set `STRIPE_WEBHOOK_SECRET` in `backend/.env`; the app boots without it, but the
webhook endpoint returns 503. With the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe/<stripe-integration-id>
stripe trigger payment_intent.succeeded
cd backend && python -m app.scripts.process_webhooks
```

Details and interview notes: [docs/stripe-webhooks.md](docs/stripe-webhooks.md).

## Testing

```bash
cd backend && source .venv/bin/activate && pytest
cd frontend && npm run lint && npm run build
```

## Current features

- PostgreSQL persistence
- GitHub OAuth + encrypted tokens + connection checks
- Provider request observability
- Failure Lab scenarios (401/403/404/429/500/timeout/malformed JSON/transport)
- Deterministic diagnosis + retryability classification
- Stripe webhooks:
  - `payment_intent.succeeded`, `payment_intent.payment_failed`, and `charge.refunded` are handled.
  - Unknown events are safely ignored.
  - Processing retries, a failed queue, and manual retry/dismiss.
- Reliability overview, per-integration health detail, failures feed, and
  request metrics (`/api/reliability/*`)
- Guided diagnostics with persisted history (`/api/diagnostics/*`)

The console opens at `http://localhost:5173/#/overview`.

## Current non-features

- AWS
- Continuous background monitoring (health is computed when requested)
- Alerts
- AI diagnosis
- Multi-user auth (operator endpoints are local prototype controls)
- Real payment mutations / Stripe API writes
- Redis / Celery / queues (the webhook worker is a CLI tick)
- Uptime, SLA, or incident statistics
- A data retention policy (evidence tables grow until pruned manually)

## Next milestone

**CI + production deployment + incident case study**
