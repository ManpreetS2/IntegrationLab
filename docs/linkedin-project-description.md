# LinkedIn project descriptions — IntegrationLab

## Short (~500 characters)

Built IntegrationLab, a self-hosted reliability console for third-party integrations. FastAPI + React + PostgreSQL separate provider requests, signed Stripe webhooks, Failure Lab simulations, and SDK-reported telemetry so operators can diagnose failures without mixing evidence types. Includes OAuth (state/PKCE), webhook retries with effect idempotency, support cases, and audit. CI validates the stack and Terraform AWS architecture (not live-deployed).

## Medium

**IntegrationLab** is a portfolio ops console for the messy middle of integrations: OAuth tokens that stop working, webhooks that arrive more than once, and client SDKs that report errors the platform did not observe itself.

I built a FastAPI/PostgreSQL backend and a React “Ledger” UI that treat those as different evidence classes. GitHub connects through an OAuth App with state and PKCE; tokens stay encrypted server-side. Stripe test-mode webhooks are signature-verified on the raw body, deduped by provider event id, processed with bounded retries (1s/2s/4s) into a failed queue, and recovered with manual retry while still applying business effects once. A Python/Node SDK lets an instrumented app report sanitized HTTP outcomes—explicitly *not* independent upstream verification.

Hardest engineering work was making recovery demos honest: delivery success vs processing failure, simulation vs live health, and claim→evidence discipline for resume wording. Six-job GitHub Actions CI and Terraform for a cost-conscious AWS topology (validated, not applied).
