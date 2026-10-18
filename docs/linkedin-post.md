# LinkedIn launch draft — IntegrationLab (Ledger UI v3)

**Status:** Ready for a final human read before posting. Pair with current Ledger UI v3 screenshots; the existing v2 video is historical, not the current UI.

I built **IntegrationLab** — a self-hosted reliability console for understanding why third-party integrations fail, what the evidence actually proves, and how to recover.

The most interesting part wasn't making API calls. It was keeping four types of evidence separate: real GitHub provider requests, signed Stripe webhook deliveries, controlled failure simulations, and HTTP outcomes reported by an application's own SDK.

Here's what I built and verified:

- **GitHub OAuth:** state + PKCE, encrypted server-side tokens, real `GET /user` diagnostics. I actually revoked IntegrationLab's authorization, observed a real HTTP 401, and reconnected to restore healthy status.
- **Stripe webhook reliability:** raw-body signature verification, duplicate-event handling, PostgreSQL-backed processing, 1s/2s/4s retries, failed-queue inspection, and manual recovery with one recorded effect. Real Stripe CLI test-mode acceptance was completed on a previous local environment; controlled processing recovery was verified locally.
- **Python + Node SDKs:** report sanitized HTTP outcomes, with one-time credential reveal, rotation, and revocation. Reports are clearly labeled as client-reported—not independently verified upstream calls.
- **Operator workflows:** Ledger UI v3, evidence-based diagnostics, support cases, and an audit trail.

The project uses FastAPI, React/TypeScript, PostgreSQL, SQLAlchemy, Alembic, Docker, and six-job GitHub Actions CI. I also defined an AWS architecture in Terraform, **but it has not been deployed**, and this is not a hosted SaaS.

The biggest lesson: a system is easier to debug when it tells you **what it knows, how it knows it, and what it doesn't know**.

GitHub: https://github.com/ManpreetS2/IntegrationLab

---

## Posting notes (do not paste this section into LinkedIn)

- Use 3–5 current Ledger UI v3 screenshots, preferably from `design/stage2/`. Avoid the older blue UI images from `docs/assets/final/` where their design no longer matches current main.
- Suggested order: Overview → Stripe failed queue → Telemetry → Support Case or Audit.
- Don't post the archived v2 demo as a current UI walkthrough.
- Claims: GitHub real OAuth + revoke/reconnect externally passed on 2026-10-17; Stripe CLI test-mode acceptance passed on an earlier local setup; AWS Terraform validated only; SDK telemetry client-reported only.
- For shorter project-section copy, use `docs/linkedin-project-description.md`.
