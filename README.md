# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting,
monitoring, debugging, and recovering third-party API and webhook integrations.

This repository is built milestone-by-milestone. The current milestone adds
**GitHub OAuth** and **provider request observability** on top of PostgreSQL
persistence.

## Current milestone: GitHub OAuth + provider observability

Working pieces:

- React + TypeScript frontend (Vite)
- FastAPI backend with Pydantic schemas
- SQLAlchemy 2.x + repository layer + PostgreSQL + Alembic
- GitHub OAuth authorization-code flow (`state` + PKCE S256)
- Encrypted access-token storage (Fernet)
- Authenticated GitHub `GET /user`
- GitHub connection profile + manual **Check connection**
- Provider API request logging (status, latency, safe errors)
- Isolated PostgreSQL test database with mocked GitHub HTTP (`respx`)

## Architecture

```text
Browser
  → React (http://localhost:5173)
  → FastAPI (http://localhost:8000)
  → GitHub OAuth / REST API
  → PostgreSQL (credentials / profile / logs)
```

See:

- [docs/architecture.md](docs/architecture.md)
- [docs/database.md](docs/database.md)
- [docs/github-oauth.md](docs/github-oauth.md) — OAuth App setup + security notes

## Prerequisites

- Python 3.11+ (3.13 works)
- Node.js 20.19+ or Node.js 22.12+ (required by Vite 8)
- Docker Desktop **or** Docker Engine + Compose (for local PostgreSQL)
  - Local Postgres.app / Homebrew Postgres also works if `DATABASE_URL` matches

## Repository layout

```text
integrationlab/
  backend/          FastAPI + SQLAlchemy + Alembic + Pytest
  frontend/         React + TypeScript (Vite)
  docs/             Architecture, database, GitHub OAuth notes
  docker/postgres/  First-boot DB init (creates integrationlab_test)
  docker-compose.yml
  .env.example
  README.md
```

## Local database (Docker Compose)

Development credentials are intentional and **not for production**:

- user / password / db: `integrationlab` / `integrationlab` / `integrationlab`
- test db: `integrationlab_test` (created on first volume init)

```bash
docker compose up -d postgres
```

PostgreSQL 18 mounts the named volume at `/var/lib/postgresql`.

## Environment setup

```bash
cp .env.example backend/.env
```

Required for persistence:

- `DATABASE_URL`
- `TEST_DATABASE_URL` (for pytest; DB name must end with `_test`)

Optional until you connect GitHub (app still boots; OAuth routes return 503):

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITHUB_OAUTH_REDIRECT_URI` (default `http://localhost:8000/api/oauth/github/callback`)
- `FRONTEND_URL` (default `http://localhost:5173`)
- `TOKEN_ENCRYPTION_KEY` (Fernet key — see [docs/github-oauth.md](docs/github-oauth.md))

Do **not** commit `backend/.env`.

## Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
```

Useful URLs:

- Liveness: `http://localhost:8000/health`
- Readiness: `http://localhost:8000/ready`
- Docs: `http://localhost:8000/docs`

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

App URL: `http://localhost:5173`

## GitHub OAuth setup (real flow)

Follow [docs/github-oauth.md](docs/github-oauth.md):

1. Create a GitHub OAuth App
2. Homepage: `http://localhost:5173`
3. Callback: `http://localhost:8000/api/oauth/github/callback`
4. Set client id/secret + Fernet key in `backend/.env`
5. Restart backend, click **Connect GitHub** on the dashboard

## Testing

```bash
cd backend
source .venv/bin/activate
export DATABASE_URL=postgresql+psycopg://integrationlab:integrationlab@localhost:5432/integrationlab
export TEST_DATABASE_URL=postgresql+psycopg://integrationlab:integrationlab@localhost:5432/integrationlab_test
pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Current features

- PostgreSQL persistence
- OAuth authorization-code flow
- `state` + PKCE
- Encrypted token at rest
- Authenticated GitHub API (`/user`)
- GitHub profile metadata
- Provider request logging
- Manual connection checks

## Current non-features (intentional)

- Failure Lab simulators
- Stripe API / webhooks
- Retries / exponential backoff / DLQ
- Redis / queues / workers
- AWS
- Application user accounts / login

## Next milestone

**Failure Lab** — controlled provider failure simulations and recovery tooling.
