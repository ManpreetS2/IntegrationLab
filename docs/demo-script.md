# Demo script — IntegrationLab (Ledger UI v3)

Audience: internship / Solutions Engineer interview.

Prefer **current external GitHub OAuth + Stripe (CLI prior / local HMAC) + SDK/recovery** evidence. Always label **SIMULATED** Failure Lab rows. Do not present Stripe CLI as re-run on the new laptop unless you actually re-ran it.

Screenshots: `docs/assets/final/`. Evidence: `docs/portfolio-evidence.md`.

---

## 2-minute backup

1. Problem (15s) — Ambiguous partner failures; mixed evidence misleads operators.  
2. Overview (20s) — Health from stored evidence; unknown ≠ healthy; Stripe degraded from failed queue.  
3. Stripe (40s) — Webhooks: signed receipt, duplicate absorbed, failed queue → manual retry story.  
4. Telemetry (25s) — SDK-reported, not verified; credential rotate/revoke.  
5. Close (20s) — FastAPI/React/Postgres/CI; AWS Terraform validated not applied; GitHub OAuth completed against github.com including revoke→reconnect.

---

## 5–7 minute engineering walkthrough

### 1. Problem (20s)

Third-party integrations fail ambiguously. Operators need provenance: provider vs webhook vs simulation vs SDK report.

### 2. Overview (25s)

`/#/overview` — attention counts, Database reachable, Stripe/SDK degraded cards. Simulations never alter live health.

### 3. Evidence sources (20s)

Say the four classes. Point at Requests / Webhooks / Failures (include simulations) / Telemetry copy.

### 4. GitHub OAuth (35s)

Show connected GitHub identity (or Connect → authorize with state + PKCE).  
Mention encrypted server-side token, Check Connection / Diagnostics as REAL `/user` probes, and the revoke→401→reconnect recovery demo.  
Keep Failure Lab simulations visually separate from those REAL rows.

### 5. Failure Lab (25s)

Run `unauthorized_401`. Show diagnosis + simulated badge. Toggle include simulations on Failures.

### 6. Stripe delivery / idempotency (45s)

Webhooks page: recent `evt_3…` processed effects. Mention CLI acceptance and `stripe events resend` → `delivery_count=2`, one effect.

### 7. Failure / recovery (50s)

Tell Demo B: delivery 2xx → processing fault → 1s/2s/4s → failed queue → manual retry → one effect. Contrast invalid signature 400.

### 8. SDK telemetry (35s)

Telemetry page: `independently_verified: no`. Credential generate/rotate/revoke narrative.

### 9. Diagnostics (20s)

Open diagnostics for Stripe/GitHub cards; explain operator-triggered probes.

### 10. Support case / audit (30s)

Open Support Cases + Audit: note, status, pinned Failure Lab evidence; SDK cannot be pinned.

### 11. Architecture / tradeoffs (25s)

Compose local; six-job CI; Terraform AWS not applied; no always-on webhook worker; single-operator.

### 12. Close (15s)

Offer deep-dive: idempotency, OAuth threat model, or evidence honesty.

---

## Recording script (90–150s) if video capability available

0–10 Overview · 10–25 real vs simulated · 25–40 SDK telemetry · 40–55 Failure Lab · 55–80 Stripe recovery · 80–100 GitHub design/handoff · 100–115 Support/audit · 115–130 architecture.  
If external GitHub not filmed, say so on screen or voiceover.
