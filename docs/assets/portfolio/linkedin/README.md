# LinkedIn launch screenshots

Five LinkedIn-ready frames for IntegrationLab. Prefer this order in a post carousel.

**Framing:** 16:9 (1600×900 or higher-resolution equivalent).  
**Environment:** local Compose full stack on `http://localhost:8080` (not AWS).  
**Safety:** no operator keys, OAuth secrets, Stripe `whsec_`, cookies, or private paths.

## Recommended order

| # | File | Subject | Capture source | Live / simulated |
|---|------|---------|----------------|------------------|
| 1 | `01-overview.png` | Reliability overview — healthy GitHub + degraded Stripe with failed queue / duplicate absorption | Reused from `docs/assets/portfolio/01-overview.png` (Oct 2026 external-acceptance session) | **Live UI** from the previously verified acceptance Compose run (stronger multi-integration health framing than the fresh-volume LinkedIn staging overview). |
| 2 | `02-github-connected.png` | Primary GitHub OAuth connection (`GitHub Developer Integration`, `@ManpreetS2`, connected status) | Reframed crop of authentic `docs/assets/portfolio/02-github-connected.png` (Oct 2026 acceptance) — primary card only | **Live GitHub OAuth** evidence from that prior run. Acceptance/deny helper integrations cropped out of frame; pixels are not invented. Fresh OAuth was not re-run for this PR. |
| 3 | `03-support-case.png` | `CASE-00001` detail — impact, pinned Failure Lab evidence, investigating status | Live Compose console, 2026-10-10 (reframed under brand chrome) | **SIMULATED** Failure Lab evidence with visible `[SIMULATED]` labels and explicit “not a live customer outage” impact text. Case workflow is live on the local stack. |
| 4 | `04-stripe-webhook.png` | Stripe webhook list — summary counters, duplicate deliveries absorbed, processed `payment_intent.succeeded` (delivery count 2) | Live Compose console, 2026-10-10 (list view; detail panel not opened) | **Locally signed demo events** (`pi_linkedin_*`) posted to the local webhook endpoint. Not a fresh Stripe CLI / Dashboard delivery. List framing avoids the known Object/Amount detail-grid collision. |
| 5 | `05-failed-queue.png` | Failed queue — `webhook_invalid_event_data`, Retry/Dismiss recovery controls | Live Compose console, 2026-10-10 | Same locally signed demo corpus as #4. Classification and operator controls are real; event payload is synthetic for the LinkedIn staging set. |

## Claims these images may support

Aligned with `docs/verification.md` / `docs/external-acceptance.md`:

- Reliability overview derives from stored evidence (no fake uptime/SLA).
- Stripe receive → verify → process path, including duplicate absorption and failed-queue classification.
- Support cases pin Failure Lab evidence without treating simulations as live customer outages.
- GitHub OAuth connected state is evidenced by the prior acceptance capture (#2), not by inventing a new OAuth session for this PR.

Do **not** claim AWS deployment, production customer metrics, a new Stripe CLI run, or a new live GitHub OAuth reconnect from the documentation-only LinkedIn QA pass.

## Visual QA

- Typography readable at LinkedIn carousel size; no credential overlays.
- Support-case `[SIMULATED]` labels retained and visible; impact text states operator exercise / not a live outage.
- Stripe #4 uses the webhook **list** (processed filter) so the Object/Amount detail-grid collision is not shown.
- GitHub #2 focuses on the primary Developer Integration card without repeated acceptance/deny rows.
- Secret string scan of PNGs: no `whsec_`, `Bearer `, or operator/OAuth secret markers.
