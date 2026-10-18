# Release readiness matrix

Date: 2026-10-17 · Branch: `feat/final-portfolio-polish` · Baseline main: `954ed0960014204bafdfaf607b47f9a7ea5179fa`

| Area | Status | Notes |
| --- | --- | --- |
| Backend | PASS | 367 pytest (re-verified on new laptop) |
| Frontend | PASS | lint, 30 unit, production build |
| Database | PASS | head `007_universal_telemetry`; outage→503→recover on new laptop |
| GitHub OAuth | PASS | 2026-10-17 native stack: interactive authorize, `/user`, diagnostics, restart persistence |
| GitHub failure recovery | PASS | Real revoke → HTTP 401 → `needs_setup` → reconnect → healthy; historical 401 retained |
| Stripe external test-mode | PASS | Prior-environment Stripe CLI sandbox (2026-10-15); not re-run on new laptop |
| Stripe idempotency | PASS | Prior CLI same-event resend + new-laptop local signed duplicate |
| Stripe retry recovery | PASS | 1s/2s/4s → failed queue → manual retry → one effect (re-verified 2026-10-17) |
| Failure Lab | PASS | Scenarios + simulation separation |
| Python SDK | PASS | Ingest/rotate/revoke |
| Node SDK | PASS | Unit suite + prior live ingest/revoke |
| Support cases | PASS | Create/note/status/pin |
| Audit | PASS | Credential + case actions; no secrets |
| Docker | PARTIAL | Compose verified earlier; Docker Desktop broken on new laptop (revoked cert) — native stack used |
| CI | PASS | PR #39 jobs green on docs commits (see Actions) |
| Terraform | PARTIAL | CI validate PASS; not applied |
| AWS live deployment | NOT VERIFIED | ARCHITECTURE VALIDATED — NOT APPLIED |
| Security | PASS | Tracked-repo pattern scan: no live secrets committed |

## Final gate checklist

- [x] current main baseline preserved (work on `feat/final-portfolio-polish` only)
- [x] stale `feat/ci-deploy-incident-case-study` tip **not** merged
- [x] backend tests / frontend lint / unit / build
- [x] current CI green
- [x] clean DB migrations
- [x] Ledger pages load (Overview→Audit); light/dark exercised (prior + operator browser on new laptop)
- [x] operator auth
- [x] Failure Lab
- [x] Python + Node SDK
- [x] support cases + audit
- [x] secret + artifact audit clean
- [x] GitHub current external OAuth — **PASS** (2026-10-17)
- [x] GitHub failure/recovery — **PASS** (2026-10-17)
- [x] Stripe external test-mode (prior CLI evidence)
- [x] Stripe invalid signature
- [x] Stripe processing recovery + effect once
- [x] database recovery (API 503 path)
- [x] screenshots under `docs/assets/final/`
- [x] README / verification / evidence docs updated

**Portfolio-ready:** yes — resume / LinkedIn / interview demo ready with honest evidence classes. AWS remains not applied. Stripe CLI was not repeated on the new laptop; prior CLI PASS is retained separately from local HMAC checks.
