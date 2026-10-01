# ADR 003: PostgreSQL as the Retry Queue

## Context
Stripe webhook processing needs durable retries without Redis/SQS/Celery for
this milestone.

## Decision
Store events and attempts in PostgreSQL. Use `FOR UPDATE SKIP LOCKED`,
`next_attempt_at`, and a CLI/UI process-due tick.

## Alternatives
- SQS + Lambda/worker
- Redis/Celery
- In-process only retries

## Tradeoffs
+ One operational database; transactional with effects  
+ Easy to inspect in the console  
− No continuous worker in AWS yet (explicit limitation)
