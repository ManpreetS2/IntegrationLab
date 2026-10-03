# LinkedIn post draft — IntegrationLab

I built **IntegrationLab**: a support and reliability console for debugging third-party API and webhook integrations.

When a partner integration breaks, the hard part usually isn’t calling the API — it’s answering what happened, what evidence matters, what the operator already tried, and how to recover without double-applying side effects.

A few engineering choices I’m happy to discuss:

1. **Evidence over vibes** — health is derived from stored provider/webhook evidence; simulations are labeled and excluded from live health.
2. **Webhook reliability in Postgres** — signature verification on the raw body, delivery dedupe, append-only attempts, bounded retries, failed queue, and effect-level idempotency — without jumping straight to Redis/Kafka.
3. **Support Cases on top of reliability** — lifecycle, pinned evidence, notes, a derived timeline (`occurred_at` vs pin time), UUID correlation, and an allowlisted operator audit trail (including intent audits before webhook side effects).
4. **Security hygiene for a portfolio system** — OAuth state + PKCE, encrypted tokens at rest, single-operator bearer gate, and an explicit threat model with honest limitations.

**Lesson:** the most useful “feature” was often the discipline *not* to build something yet — no fake multi-tenant RBAC, no premature distributed tracing, no claiming AWS was deployed until it actually is.

**Stack:** FastAPI · React · PostgreSQL · Docker · GitHub Actions · Terraform (AWS architecture)

GitHub: https://github.com/ManpreetS2/IntegrationLab
