# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting, monitoring, debugging, and recovering third-party API and webhook integrations.

This repository is being built step-by-step as a learning project. The current milestone replaces Day 1 in-memory storage with durable **PostgreSQL** persistence.

## Current milestone: PostgreSQL persistence

Working pieces:

- React + TypeScript frontend (Vite) — same API contract as Day 1
- FastAPI backend with Pydantic request/response models
- SQLAlchemy 2.x ORM + repository data-access layer
- PostgreSQL 18 via Docker Compose
- Alembic migrations (no runtime `create_all()`)
- Idempotent seed for GitHub and Stripe demo integrations
- Liveness (`GET /health`) and readiness (`GET /ready`)
- Isolated PostgreSQL test database for Pytest

## Architecture

```text
Browser
  → React (http://localhost:5173)
  → HTTP/JSON
  → FastAPI (http://localhost:8000)
  → repository / data access
  → SQLAlchemy
  → PostgreSQL
```

See:

- [docs/architecture.md](docs/architecture.md) — request path
- [docs/database.md](docs/database.md) — Engine, Session, transactions, Alembic

## Prerequisites

- Python 3.11+ (3.13 works)
- Node.js 20.19+ or Node.js 22.12+ (required by Vite 8)
- Docker Desktop **or** Docker Engine + Compose (for local PostgreSQL)

## Repository layout

```text
integrationlab/
  backend/          FastAPI + SQLAlchemy + Alembic + Pytest
  frontend/         React + TypeScript (Vite)
  docs/             Architecture + database learning notes
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
# from repository root
docker compose up -d postgres
```

PostgreSQL 18 mounts the named volume at `/var/lib/postgresql` (the image's
declared data root), not the older `/var/lib/postgresql/data` path used by
PostgreSQL 17 and earlier.

Wait until healthy, then confirm:

```bash
docker compose ps
docker compose exec postgres pg_isready -U integrationlab -d integrationlab
```

### Data survival / destructive reset

- `docker compose stop` or `docker compose down` — keeps the named volume (`postgres_data`)
- `docker compose down -v` — **DESTROYS** local database data

Manual destructive reset (explicit only):

```bash
docker compose down -v
docker compose up -d postgres
cd backend
source .venv/bin/activate
alembic upgrade head
python -m app.scripts.seed
```

## Environment setup

```bash
# from repository root
cp .env.example backend/.env
```

Do **not** commit `backend/.env`.

Default values point at the Docker Compose Postgres instance.

## Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Migrations

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

Alembic applies checked-in migration files. Editing an ORM class alone does **not** change an existing database.

### Seed demo data

```bash
cd backend
source .venv/bin/activate
python -m app.scripts.seed
```

Idempotent: running seed again does not create duplicate GitHub/Stripe rows.

### Run the API

```bash
cd backend
source .venv/bin/activate
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

Default API URL: `http://localhost:8000` (override with `VITE_API_URL` if needed).

## Testing

Tests use `TEST_DATABASE_URL` / `integrationlab_test` and refuse to run unless
the database name ends with `_test`.

```bash
cd backend
source .venv/bin/activate
# ensure Postgres is up and migrations can run against the test DB
export DATABASE_URL=postgresql+psycopg://integrationlab:integrationlab@localhost:5432/integrationlab
export TEST_DATABASE_URL=postgresql+psycopg://integrationlab:integrationlab@localhost:5432/integrationlab_test
pytest
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

## Database inspection (independent of React/FastAPI)

```bash
docker compose exec postgres psql -U integrationlab -d integrationlab
```

Then:

```sql
SELECT id, name, provider, status, created_at
FROM integrations;
```

## Current limitations (intentional)

- No OAuth / no real GitHub or Stripe API calls
- No webhooks, retries, Redis, queues, or AWS
- No authentication / users
- No API request logging yet
- provider/status stored as strings (not Postgres native ENUMs)

## Next milestone

GitHub OAuth + first real provider connection.
