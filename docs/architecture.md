# IntegrationLab Architecture — Day 1

This document explains the Day 1 foundation in plain language. The goal is
to make the request path obvious before we add databases, OAuth, queues,
or cloud infrastructure.

## High-level flow

```text
Browser
  → React (Vite frontend on http://localhost:5173)
  → HTTP/JSON request
  → FastAPI route (backend on http://localhost:8000)
  → In-memory data store (Python list in process memory)
  → JSON response
  → React state update
  → Rendered UI
```

Day 1 is intentionally a straight line. There is no database layer, no
auth middleware, and no background worker between the route and the data.

## GET /api/integrations

What happens when the dashboard loads or refreshes:

1. The browser opens the React app.
2. React runs a `fetch` (or similar) to `GET http://localhost:8000/api/integrations`.
3. FastAPI receives the request and matches the integrations list route.
4. The route asks the in-memory store for every integration.
5. The store returns the current Python list of Pydantic `Integration` models.
6. FastAPI serializes those models to JSON and sends the response.
7. React parses the JSON into TypeScript objects and stores them in component state.
8. The UI renders summary cards and the integrations table from that state.

Seeded Day 1 data includes two integrations:

- GitHub (`provider: github`, `status: not_connected`)
- Stripe (`provider: stripe`, `status: not_connected`)

## POST /api/integrations

What happens when you submit the create form:

1. You enter a display name and choose a provider in the React form.
2. React sends `POST http://localhost:8000/api/integrations` with a JSON body such as:

```json
{
  "name": "Acme GitHub",
  "provider": "github"
}
```

3. FastAPI validates the body with the Pydantic `IntegrationCreate` model.
4. The route asks the in-memory store to create a new integration.
5. The store generates:
   - `id` (UUID)
   - `created_at` (UTC timestamp)
   - default `status` (`not_connected`)
   - `last_checked_at` (`null` for Day 1)
6. The new record is appended to the in-memory list.
7. FastAPI returns HTTP **201** with the full integration JSON.
8. React updates local state (often by re-fetching the list) and the table shows the new row.

## Backend layout (Day 1)

| Path | Role |
|------|------|
| `backend/app/main.py` | Creates the FastAPI app and enables CORS |
| `backend/app/api/health.py` | `GET /health` |
| `backend/app/api/integrations.py` | Integration list/create routes |
| `backend/app/models/integration.py` | Pydantic request/response models |
| `backend/app/services/integration_store.py` | In-memory store + seed data |
| `backend/app/core/config.py` | Local CORS settings |
| `backend/tests/test_api.py` | Basic foundation tests |

## Frontend layout (Day 1)

| Path | Role |
|------|------|
| `frontend/src/App.tsx` | Dashboard screen |
| `frontend/src/api.ts` | Typed HTTP helpers |
| `frontend/src/types.ts` | TypeScript types matching the API |
| `frontend/src/components/` | Summary cards, table, and create form |

## Day 1 limitations (intentional)

These are deliberate learning boundaries, not forgotten features:

- **No persistence yet** — data lives only in memory
- **Data disappears when the backend restarts**
- **No OAuth** — providers are names only
- **No external provider API calls** — GitHub/Stripe are not contacted
- **No webhooks**
- **No retry system**
- **No authentication**
- **No real health calculations yet** — summary cards count statuses only

## Why this shape matters

By keeping Day 1 small, you can see every hop clearly:

```text
UI event → HTTP → route → store → response → UI state → render
```

Later milestones will replace the in-memory store with PostgreSQL, then
add OAuth, provider API checks, webhooks, and recovery workflows one layer
at a time.
