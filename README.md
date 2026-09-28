# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting,
monitoring, debugging, and recovering third-party API integrations.

## Current milestone: Failure Lab + deterministic diagnosis

Working pieces:

- React + TypeScript frontend
- FastAPI + PostgreSQL + SQLAlchemy + Alembic
- GitHub OAuth (state + PKCE + encrypted tokens)
- Provider request logging
- **Failure Lab** — sandboxed scenario simulator
- Deterministic diagnosis from observed evidence
- Simulated vs real request log badges

## Architecture

Real provider path:

```text
GitHub → ProviderHttpResult → request log (real)
```

Failure Lab path:

```text
Simulator → ProviderHttpResult → request log (simulated) → diagnosis → failure run
```

Simulated failures **do not** affect real provider connection state and **do not**
decrypt or use real OAuth credentials.

See:

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
- Deterministic diagnosis + retryability classification (no auto-retry)

## Current non-features

- Automatic retries / backoff / DLQ
- Stripe webhooks
- Redis / queues / AWS
- AI diagnosis
- App user authentication

## Next milestone

**Stripe webhooks + idempotency + retry policy**
