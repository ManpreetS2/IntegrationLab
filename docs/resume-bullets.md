# Resume bullets — IntegrationLab

Rewrite to match your resume voice. Prefer bullets that match **actual verification status**.

## Strong (CI + architecture; no false AWS deploy claim)

- Built an integration reliability and support console with FastAPI, React, PostgreSQL, and Docker, implementing GitHub OAuth (state + PKCE), Fernet-encrypted credentials, Stripe-signed webhook ingestion, delivery deduplication, idempotent effects, bounded retries, guided diagnostics, and support-case workflows with correlation IDs and an operator audit trail.

- Designed webhook recovery using a durable PostgreSQL-backed attempt history, failed queue, and effect-level idempotency; validated behavior with a full pytest suite and an assembled Compose smoke workflow in CI.

- Implemented Support Cases as first-class investigations (lifecycle, severity, evidence pinning, derived timeline) with UUID correlation via ContextVar and pre-side-effect intent auditing for operator webhook actions.

- Authored Terraform for a cost-conscious AWS portfolio topology (CloudFront, S3, ALB, ECS/Fargate, RDS, Secrets Manager, GitHub OIDC) and a migrate-before-deploy CD workflow; infrastructure is validated in CI and applied only with explicit approval.

## Shorter variants

- Built a FastAPI/React/Postgres integration ops console with OAuth/PKCE, encrypted tokens, Stripe webhook reliability, Failure Lab simulations, diagnostics, and support-case/audit tooling.

- Separated simulated Failure Lab evidence from live health scoring and enforced secret-safe observability and audit metadata allowlists.

## Avoid until true

- Do **not** say “deployed to AWS” unless `terraform apply` and runtime acceptance completed.
- Do **not** say “externally verified GitHub/Stripe” until those runbook steps succeed (see `docs/external-acceptance.md` / `docs/verification.md`).
