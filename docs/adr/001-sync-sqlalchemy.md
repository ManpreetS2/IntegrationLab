# ADR 001: Sync SQLAlchemy Sessions

## Context
IntegrationLab needs durable PostgreSQL access for OAuth, request logs, and
Stripe webhook receipt/processing. FastAPI supports async, but the existing
codebase and libraries are sync-first.

## Decision
Use SQLAlchemy 2.x **sync** engine/sessions. For the async Stripe webhook route,
open a Session **inside** the threadpool worker so Sessions are never shared
across threads.

## Alternatives
- Async SQLAlchemy + asyncpg throughout
- One global Session (unsafe)

## Tradeoffs
+ Simpler mental model and mature tooling  
+ Clear request-scoped units of work  
− Need care at async boundaries (documented and tested)
