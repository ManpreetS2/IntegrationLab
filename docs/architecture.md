# IntegrationLab Architecture — PostgreSQL Persistence

Day 1 taught the straight HTTP path with an in-memory list. This milestone
keeps the same public API and replaces the list with PostgreSQL.

## High-level flow (current)

```text
Browser
  → React (http://localhost:5173)
  → HTTP/JSON request
  → FastAPI route
  → request-scoped SQLAlchemy Session (get_db)
  → IntegrationRepository
  → SQLAlchemy statement
  → psycopg
  → PostgreSQL
  → ORM objects
  → Pydantic API models
  → JSON response
  → React state
  → rendered UI
```

## GET /api/integrations

1. React calls `GET http://localhost:8000/api/integrations`.
2. FastAPI matches the list route.
3. `Depends(get_db)` opens a request-scoped Session from the shared Engine.
4. The route calls `IntegrationRepository.list_all(session)`.
5. SQLAlchemy issues a `SELECT` on `integrations`.
6. Rows become `IntegrationORM` objects, then Pydantic `Integration` models.
7. FastAPI returns JSON. React stores and renders it.

## POST /api/integrations

1. React submits `{ "name": "...", "provider": "github" }`.
2. Pydantic `IntegrationCreate` validates and trims the name.
3. The route receives a Session via `get_db`.
4. The repository creates an `IntegrationORM`, `session.add()`, `commit()`, `refresh()`.
5. PostgreSQL persists the row inside a transaction.
6. FastAPI returns HTTP **201** with the full integration JSON.
7. React appends the returned object to local state (no dependency on storage internals).

## Why React does not talk to PostgreSQL

Correct:

```text
React → HTTP → FastAPI → repository → SQLAlchemy → PostgreSQL
```

Incorrect:

```text
React → PostgreSQL
```

Reasons:

- Database credentials stay on the backend
- The API enforces validation and business rules
- Frontend code does not depend on table schemas
- The database can evolve without rewriting the UI

## Layers

| Layer | Role |
|-------|------|
| Pydantic models (`app/models`) | HTTP request/response validation |
| ORM models (`app/db/models`) | Table mapping |
| Repository (`app/repositories`) | Database operations |
| Routes (`app/api`) | HTTP behavior |
| Alembic (`alembic/versions`) | Schema history |

## Health vs readiness

- `GET /health` — **liveness**: process is up (does not query Postgres)
- `GET /ready` — **readiness**: Postgres answers `SELECT 1`

## Day 1 → current change

| Day 1 | Now |
|-------|-----|
| `IntegrationStore` + Python list | `IntegrationRepository` + PostgreSQL |
| Data gone on restart | Data survives backend restart |
| No migrations | Alembic `001_create_integrations` |

## Intentional non-goals (later milestones)

- GitHub OAuth / Stripe APIs / webhooks
- Request logging, retries, Redis, queues, AWS
- Authentication / users

## Related docs

- [database.md](database.md) — Engine, Session, transactions, Alembic learning notes
