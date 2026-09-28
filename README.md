# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting, monitoring, debugging, and recovering third-party API and webhook integrations.

This repository is being built step-by-step as a learning project. Day 1 intentionally stops at a working React + FastAPI foundation with in-memory data.

## Current milestone: Day 1 foundation

Working pieces:

- React + TypeScript frontend (Vite)
- FastAPI backend with Pydantic models
- `GET /health`
- `GET /api/integrations`
- `POST /api/integrations`
- In-memory seed data for GitHub and Stripe
- Basic Pytest coverage
- Architecture notes in `docs/architecture.md`

## Architecture (Day 1)

```text
Browser
  → React (http://localhost:5173)
  → HTTP/JSON
  → FastAPI (http://localhost:8000)
  → In-memory Python list
  → JSON response
  → React state
  → Dashboard UI
```

See [docs/architecture.md](docs/architecture.md) for the full walkthrough of GET and POST flows.

## Repository layout

```text
integrationlab/
  backend/          FastAPI app + Pytest
  frontend/         React + TypeScript (Vite)
  docs/             Architecture notes
  docker-compose.yml   Placeholder only (not required for Day 1)
  README.md
  .gitignore
```

## Backend setup

Requirements: Python 3.11+ recommended.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API base URL: `http://localhost:8000`

Useful checks:

- Health: `http://localhost:8000/health`
- Docs: `http://localhost:8000/docs`

## Frontend setup

Requirements: Node.js 18+.

```bash
cd frontend
npm install
npm run dev
```

App URL: `http://localhost:5173`

The frontend talks to `http://localhost:8000` by default. You can override that with `VITE_API_URL` if needed.

## Testing

From the `backend` directory with the virtualenv active:

```bash
cd backend
source .venv/bin/activate
pytest
```

Day 1 tests cover:

1. `GET /health`
2. `GET /api/integrations`
3. `POST /api/integrations`

## Current limitations (intentional)

- Persistence does not exist yet
- Data disappears when the backend restarts
- No OAuth
- No external provider API calls
- No webhooks
- No retry system
- No authentication
- No real health calculations yet
- Docker is not required (compose file is a placeholder)

These limits are deliberate so the request path stays easy to understand.

## Next milestone

Replace the in-memory store with PostgreSQL persistence while keeping the same API shape and dashboard behavior.
