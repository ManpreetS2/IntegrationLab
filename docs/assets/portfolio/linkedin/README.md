# LinkedIn launch screenshots

Five LinkedIn-ready frames for IntegrationLab. Prefer this order in a post carousel.

**Framing:** 16:9 (captures at 1600×900 CSS viewport / 3840×2160 device pixels unless noted).  
**Environment:** local Compose full stack on `http://localhost:8080` (not AWS).  
**Safety:** no operator keys, OAuth secrets, Stripe `whsec_`, cookies, or private paths.

## Recommended order

| # | File | Subject | Capture source | Live / simulated |
|---|------|---------|----------------|------------------|
| 1 | `01-overview.png` | Reliability overview — DB healthy, Stripe degraded with failed queue + duplicate absorption | Live Compose console, 2026-10-10 | **Live UI** over local stack. Stripe counters reflect locally HMAC-signed test events (not Stripe CLI / Dashboard push). GitHub shown **not connected** after a fresh volume. |
| 2 | `02-github-connected.png` | Connected GitHub OAuth (`@ManpreetS2`, safe profile metadata) | Reused from `docs/assets/portfolio/02-github-connected.png` (Oct 2026 external-acceptance run) | **Live GitHub OAuth** evidence from that prior run. Fresh OAuth could not be completed in this session (browser hit GitHub sign-in). |
| 3 | `03-support-case.png` | `CASE-00001` detail — pinned Failure Lab evidence, investigating status, timeline | Live Compose console, 2026-10-10 | **SIMULATED** Failure Lab evidence (`rate_limited_429`, `unauthorized_401`) with visible `[SIMULATED]` labels. Case workflow itself is live on the local stack. |
| 4 | `04-stripe-webhook.png` | Verified `payment_intent.succeeded` — processed, signature verified, duplicate delivery absorbed, effect applied | Live Compose console, 2026-10-10 | **Locally signed demo events** (`evt_linkedin_*` / `pi_linkedin_*`) posted to the local webhook endpoint with the configured signing secret. Not a fresh Stripe CLI or Dashboard delivery. |
| 5 | `05-failed-queue.png` | Failed queue — `webhook_invalid_event_data`, Retry/Dismiss recovery controls | Live Compose console, 2026-10-10 | Same locally signed demo corpus as #4. Classification and operator controls are real; event payload is synthetic for the LinkedIn staging set. |

## Claims these images may support

Aligned with `docs/verification.md` / `docs/external-acceptance.md`:

- Reliability overview derives from stored evidence (no fake uptime/SLA).
- Stripe receive → verify → process path, including duplicate absorption and failed-queue classification.
- Support cases pin Failure Lab evidence without treating simulations as live customer outages.
- GitHub OAuth connected state is evidenced by the prior acceptance capture (#2), not by this session’s fresh DB.

Do **not** claim AWS deployment, production customer metrics, or a new Stripe CLI / live GitHub OAuth run from the 2026-10-10 LinkedIn staging session alone.

## Visual QA (2026-10-10)

- Typography readable at LinkedIn carousel size; no credential overlays.
- Support-case and Failure Lab `[SIMULATED]` labels retained and visible.
- Stripe detail may show a known minor Object/Amount grid overlap (pre-existing UI); content remains legible.
- Secret string scan of PNGs: no `whsec_`, `Bearer `, or operator/OAuth secret markers.
