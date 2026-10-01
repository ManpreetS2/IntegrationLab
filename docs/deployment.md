# Deployment & Rollback

## Happy path

0. Run from `main` only (workflow guard + GitHub Environment branch restriction).
1. Build/push backend image tagged with the Git commit SHA.
2. Register a new ECS task definition revision referencing that SHA.
3. Run a one-off ECS task with command `alembic upgrade head`.
4. Abort if the migration exit code is non-zero.
5. Update the ECS service to the new task definition at desired count **1**;
   wait for stability (min healthy 100% / max 200%, circuit breaker rollback).
6. Build the frontend with `VITE_API_URL=""` (same-origin).
7. Sync `frontend/dist` to the private S3 bucket.
8. Invalidate CloudFront (`/index.html` and `/*`).
9. Smoke test `/health`, `/ready`, `/api/reliability/system` through CloudFront.

Scale-to-zero for cost control is manual (`aws ecs update-service --desired-count 0`)
and is not a successful deploy outcome.

Images are immutable SHA tags in ECR. That creates the chain:

```text
Git SHA → ECR image → ECS task definition revision
```

## Why migrate before service deploy

Running migrations on every container boot races multiple tasks and can leave the
fleet half-migrated. A single one-off task with the **new** image applies schema
changes once, then the service rolls forward.

## Rollback

### Backend application

1. Identify the previous healthy task definition revision (or previous SHA).
2. `aws ecs update-service --task-definition <previous> --force-new-deployment`
3. Wait for service stability.
4. Confirm `/health` and `/ready` through CloudFront.

Do **not** redeploy only a `latest` tag — SHA tags make rollback unambiguous.

### Frontend

1. Rebuild the previous Git SHA with `VITE_API_URL=""`, or
2. Re-upload a retained `dist/` artifact for that SHA.
3. Sync to S3 and invalidate CloudFront.

### Database migrations (hardest part)

Application rollback must **not** automatically run `alembic downgrade` in
production. Downgrades can destroy data and are rarely tested under load.

Strategy:

- Prefer **forward-compatible** migrations (expand → migrate app → contract).
- Existing revisions `001`–`005` remain as-is; do not rewrite them.
- If a bad migration shipped, fix forward with a new revision after investigation.
- Restore from RDS snapshot only as a last resort (portfolio retention is 1 day).

This is a deliberate interview talking point: rolling back containers is cheap;
rolling back schema is not.

## Health vs readiness during deploys

- ALB health check: `GET /health` (process alive).
- Readiness: `GET /ready` (PostgreSQL reachable).

Using `/ready` as the ALB check would remove every task during a brief DB blip.
Liveness keeps the fleet registered while `/ready` and the reliability console
surface database unavailability honestly.

## Smoke tests (non-destructive)

After deploy, only read-only checks run:

- `GET /health` → 200
- `GET /ready` → database reachable
- `GET /api/reliability/system` → database healthy
- Frontend root returns HTML

No production OAuth or destructive webhook tests run in the deploy workflow.
