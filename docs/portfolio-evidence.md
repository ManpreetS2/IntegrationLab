# Claim → Evidence Matrix

> **Dated acceptance record:** the test evidence below is from 2026-10-15 to 2026-10-17, before PR #39 and PR #40 were merged. Current `main` advanced to `94f0c6d` (Ledger spacing/mobile fixes), with six-job CI passing. These older acceptance SHA references are intentionally retained for provenance; they are not the current main HEAD.

Governing document for README, resume, and interview wording.
Date of this run: **2026-10-15** (America/Los_Angeles) / **2026-10-16 UTC**.
Baseline `main` SHA: `954ed0960014204bafdfaf607b47f9a7ea5179fa`.
Acceptance branch: `feat/final-portfolio-polish`.
Environment: local Docker Compose (`docker-compose.full.yml`) on `localhost:8080` / `:8000`.

Allowed statuses:

- `VERIFIED CURRENT EXTERNAL`
- `VERIFIED CURRENT LOCAL`
- `VERIFIED CURRENT AUTOMATED`
- `VERIFIED HISTORICAL EXTERNAL`
- `MOCKED / DETERMINISTIC TEST`
- `ARCHITECTURE ONLY`
- `NOT VERIFIED`
- `DO NOT CLAIM`

| Claim | Evidence | Evidence type | Current? | Safe public wording | Status |
| --- | --- | --- | --- | --- | --- |
| FastAPI + React + PostgreSQL + Alembic stack runs | Compose stack healthy; OpenAPI + Ledger UI | local | yes | “Local Compose stack runs the FastAPI API and Ledger UI against PostgreSQL.” | VERIFIED CURRENT LOCAL |
| Alembic head applies cleanly | `alembic heads` → `007_universal_telemetry`; disposable upgrade | automated + local | yes | “Migrations apply cleanly to head `007_universal_telemetry`.” | VERIFIED CURRENT AUTOMATED |
| Backend pytest suite green | `pytest` in `backend/` → **367 passed** | automated | yes | “Backend suite: 367 passed.” | VERIFIED CURRENT AUTOMATED |
| Frontend lint / unit / production build | `npm run lint` exit 0; `npm test:unit` 30; `VITE_API_URL= npm run build` | automated | yes | “Frontend lint, 30 unit tests, and production build pass.” | VERIFIED CURRENT AUTOMATED |
| Six-job CI green on main | GitHub Actions run on `954ed09` success | external CI | yes | “Current main CI is green (backend, frontend, containers, smoke, Terraform).” | VERIFIED CURRENT EXTERNAL |
| GitHub OAuth connect uses state + PKCE S256 | Connect `302` to `github.com` with `state`, `code_challenge`, `S256` | local code path | yes | “Connect handoff includes OAuth state and PKCE S256.” | VERIFIED CURRENT LOCAL |
| GitHub OAuth completes against github.com (current Ledger) | 2026-10-17 native `:8080`: operator consent → connected `ManpreetS2`; Check Connection + Diagnostics pass; REAL `/user` | external | yes | “Completed GitHub OAuth against github.com on the current Ledger UI with encrypted token persistence.” | VERIFIED CURRENT EXTERNAL |
| GitHub revoke → detect → reconnect recovery | 2026-10-17: revoke IntegrationLab OAuth App only → REAL 401 → `needs_setup` → reconnect → healthy; historical 401 retained | external | yes | “After revoking the OAuth App grant, Check Connection and Diagnostics detected real unauthorized `/user` calls; reconnect restored health.” | VERIFIED CURRENT EXTERNAL |
| Stripe test-mode webhook accepted (CLI) | `stripe listen --all-snapshot` → HTTP 200; events `evt_3…` | external | yes | “Stripe CLI test/sandbox webhooks were accepted with signature verification on 2026-10-15.” | VERIFIED CURRENT EXTERNAL |
| `payment_intent.succeeded` → `payment_success_recorded` | Provider event processed; effect recorded | external | yes | “Succeeded payment_intent processed to `payment_success_recorded`.” | VERIFIED CURRENT EXTERNAL |
| `payment_intent.payment_failed` → `payment_failure_recorded` | Provider event processed | external | yes | “Failed payment_intent processed to `payment_failure_recorded`.” | VERIFIED CURRENT EXTERNAL |
| `charge.refunded` → `refund_recorded` | Provider event processed | external | yes | “Refund event processed to `refund_recorded`.” | VERIFIED CURRENT EXTERNAL |
| Unknown/unsupported Stripe types ignored safely | Related CLI events ignored; no false failure | external | yes | “Unsupported event types are stored and marked ignored.” | VERIFIED CURRENT EXTERNAL |
| Invalid Stripe signature rejected | Local POST → HTTP 400; no event row | local | yes | “Invalid signatures return 400 and create no trusted event.” | VERIFIED CURRENT LOCAL |
| Same Stripe event redelivery is idempotent | `stripe events resend` → `delivery_count=2`, one row, one effect | external | yes | “Same provider event redelivery increments delivery_count and keeps one effect.” | VERIFIED CURRENT EXTERNAL |
| Stripe processing retry 1s/2s/4s then failed queue | Controlled local demo on Compose DB + pytest | local + automated | yes | “Retryable processing failures back off 1s/2s/4s then enter the failed queue.” | VERIFIED CURRENT LOCAL |
| Manual retry recovers with exactly one effect | Failed demo event → retry → process → 1 effect | local | yes | “Manual retry after failed queue recovered with a single effect.” | VERIFIED CURRENT LOCAL |
| Failure Lab scenarios are simulated and isolated | `unauthorized_401` run; failures `include_simulated` | local | yes | “Failure Lab marks simulations and does not set live provider health.” | VERIFIED CURRENT LOCAL |
| Python SDK ingest + rotate + revoke | Live Compose Orders API credential lifecycle | local | yes | “Python SDK telemetry accepted; rotated/revoked credentials rejected with 401.” | VERIFIED CURRENT LOCAL |
| Node SDK ingest + revoke | Live Compose Node client | local | yes | “Node SDK telemetry accepted; revoked credential rejected.” | VERIFIED CURRENT LOCAL |
| SDK telemetry is not upstream verification | API `independently_verified: false`; UI copy | local | yes | “SDK rows are client-reported, not independently verified.” | VERIFIED CURRENT LOCAL |
| Support cases + notes + status + reopen | CASE-00010 lifecycle + timeline | local | yes | “Support cases support notes, status changes, and reopen.” | VERIFIED CURRENT LOCAL |
| Eligible evidence pin; SDK not pinnable | Pin `failure_lab_run` 201; `sdk_telemetry` 422 | local | yes | “SDK observations cannot be pinned as case evidence.” | VERIFIED CURRENT LOCAL |
| Operator auth gate | Unauth/invalid → 401; `/auth/operator` JSON via `:8080` | local | yes | “Operator mutations require a valid bearer key.” | VERIFIED CURRENT LOCAL |
| Audit trail without secrets | `/api/audit-events` actions; no `whsec_` / tokens | local | yes | “Operator actions are audited without embedding secrets.” | VERIFIED CURRENT LOCAL |
| Database outage → API safe failure → recovery | Postgres stop → integrations 503; start → 200 | local | yes | “With Postgres down, data APIs return 503; after restart, data returns.” | VERIFIED CURRENT LOCAL |
| AWS live deployment | Terraform validate only; no apply | architecture | no | “AWS topology is Terraform-validated, not applied.” | ARCHITECTURE ONLY / DO NOT CLAIM “hosted on AWS” |
| Enterprise RBAC / multi-tenant | Not implemented | — | no | Do not claim. | DO NOT CLAIM |
| Continuous webhook worker | Operator/process-due only | — | no | “Processing is on-demand, not a always-on worker.” | DO NOT CLAIM continuous worker |
| Production / battle-tested / enterprise-grade | Portfolio project | — | no | Do not use these adjectives. | DO NOT CLAIM |
