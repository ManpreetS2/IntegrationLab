# Release readiness matrix

Date: 2026-10-15 · Baseline: `954ed0960014204bafdfaf607b47f9a7ea5179fa` · Branch: `feat/final-portfolio-polish`

| Area | Status | Notes |
| --- | --- | --- |
| Backend | PASS | 367 pytest |
| Frontend | PASS | lint, 30 unit, production build |
| Database | PASS | head `007_universal_telemetry`; clean upgrade; outage→503→recover |
| GitHub OAuth | BLOCKED | PKCE/state connect verified; interactive authorize not completed |
| GitHub failure recovery | BLOCKED | Depends on connected grant |
| Stripe external test-mode | PASS | CLI sandbox listen + triggers |
| Stripe idempotency | PASS | External same-event resend + effect once |
| Stripe retry recovery | PASS | 1s/2s/4s → failed queue → manual retry → one effect |
| Failure Lab | PASS | Scenarios + simulation separation |
| Python SDK | PASS | Ingest/rotate/revoke |
| Node SDK | PASS | Ingest/revoke |
| Support cases | PASS | Create/note/status/reopen/pin |
| Audit | PASS | Credential + case actions; no secrets |
| Docker | PASS | Compose full stack; image without `.env` |
| CI | PASS | Main green on baseline SHA |
| Terraform | PARTIAL | CI validate PASS; local provider plugin timeout |
| AWS live deployment | NOT VERIFIED | ARCHITECTURE VALIDATED — NOT APPLIED |
| Security | PASS | Tracked-repo pattern scan: no live secrets committed |

## Final gate checklist

- [x] current main baseline preserved (work on `feat/final-portfolio-polish` only)
- [x] stale `feat/ci-deploy-incident-case-study` tip **not** merged
- [x] backend tests / frontend lint / unit / build
- [x] current CI green
- [x] clean DB migrations
- [x] Ledger pages load (Overview→Audit); light/dark exercised
- [x] operator auth
- [x] Failure Lab
- [x] Python + Node SDK
- [x] support cases + audit
- [x] secret + artifact audit clean
- [ ] GitHub current external OAuth — **BLOCKED**
- [ ] GitHub failure/recovery — **BLOCKED**
- [x] Stripe external test-mode
- [x] Stripe invalid signature
- [x] Stripe processing recovery + effect once
- [x] database recovery (API 503 path)
- [x] screenshots under `docs/assets/final/`
- [x] README / verification / evidence docs updated

**Portfolio-ready with honest blockers:** yes — resume/interview ready if GitHub external is labeled BLOCKED and Stripe/SDK/recovery claims stay accurate.
