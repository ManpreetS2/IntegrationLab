# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting,
monitoring, debugging, and recovering third-party API integrations.

## Current milestone: Stripe Webhooks + Idempotency + Retry Engine

Working pieces:

- React + TypeScript frontend
- FastAPI + PostgreSQL + SQLAlchemy + Alembic
- GitHub OAuth (state + PKCE + encrypted tokens)
- Provider request logging (outbound)
- Failure Lab: a sandboxed scenario simulator with deterministic diagnosis
- **Stripe webhooks**:
  - Official SDK signature verification on the exact raw body.
  - Durable receipt with a quick 2xx.
  - Duplicate delivery dedupe and effect-level idempotency.
  - Handler registry.
  - Deterministic 1s/2s/4s retries.
  - Failed queue with manual retry and dismiss.
  - Dashboard section.

## Architecture

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

## Current non-features

- Real payment mutations / Stripe API writes
- Redis / Celery / queues / AWS (the worker is a CLI tick)
- AI diagnosis
- App user authentication (operator endpoints are local prototype controls)

## Next milestone

**Reliability Dashboard + guided diagnostics**
