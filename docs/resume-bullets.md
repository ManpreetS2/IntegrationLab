# Resume bullets — IntegrationLab

Rewrite to match your voice. Align every claim with `docs/portfolio-evidence.md`.

## Strong options (4–6)

1. Built an integration reliability console (FastAPI, React, PostgreSQL, Docker) that separates provider requests, signed Stripe webhooks, Failure Lab simulations, and SDK-reported telemetry so operators diagnose failures from stored evidence without mixing sources.

2. Implemented GitHub OAuth with state + PKCE and Fernet-encrypted server-side tokens, plus Stripe webhook ingestion with raw-body signature verification, provider-event deduplication, bounded retries (1s/2s/4s), a failed queue, and effect-level idempotency (one business effect after retries and redelivery).

3. Demonstrated Stripe test-mode acceptance via Stripe CLI (including same-event redelivery) and a controlled processing-failure recovery path ending in manual retry with a single recorded effect.

4. Shipped Python and Node SDKs for sanitized HTTP outcome ingestion with one-time credential reveal, rotation, and revocation—explicitly labeled as client-reported, not independent upstream verification.

5. Added support-case workflows (notes, status, eligible evidence pinning) and an operator audit trail that excludes secrets; enforced with a 300+ test backend suite and six-job GitHub Actions CI.

6. Authored Terraform for a cost-conscious AWS portfolio topology (CloudFront, S3, ALB, ECS/Fargate, RDS, Secrets Manager, GitHub OIDC); validated in CI and **not** applied without explicit approval.

## Do not write

- “Hosted on AWS” / “production-tested” / “enterprise-grade” / “battle-tested”
- “SDK verifies upstream provider behavior”
- “GitHub OAuth externally verified on \<date\>” unless you completed interactive authorize in that window
