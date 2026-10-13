# UI redesign screenshots (Oct 2026)

Authentic captures from the running Compose app at `http://127.0.0.1:8080`
on branch `feat/final-ui-ux-polish`. Desktop frames are **1600×900**.
Mobile frames are **390×844**.

Operator walkthrough: [DEMO_GUIDE.md](./DEMO_GUIDE.md).

| File | Subject | Evidence |
|------|---------|----------|
| `01-overview.png` | Sidebar, health counts, Stripe degraded card | Stored webhook evidence. GitHub is not connected. Failure Lab does not change live health. |
| `02-integrations.png` | GitHub connect cards and Stripe endpoint | No OAuth token and no webhook secret. Verification shows **Configured** only. |
| `03-requests.png` | Source filter **Simulated only** | Failure Lab simulations, badged Simulated. Not real GitHub traffic. |
| `04-webhooks.png` | Counters, duplicate delivery count 2, long object id | Locally HMAC-signed synthetic test events. Not Stripe infrastructure deliveries. |
| `05-failed-queue.png` | Selected processed event plus failed queue, Retry/Dismiss | Same locally signed corpus. `webhook_invalid_event_data` is a real processing result. |
| `06-failure-lab.png` | 429 scenario, observed result, diagnosis | Explicitly simulated. |
| `07-diagnostics.png` | Stripe health, previous run, checks | Stored-evidence diagnostics. Secret value is not shown. |
| `08-support-case.png` | CASE-00007 detail, note, timeline | Case is real app data pinned to a **simulated** Failure Lab run. |
| `09-audit.png` | Operator audit from the showcase workflow | Real audit rows. No payloads or secrets. |
| `10-unlock.png` | Operator unlock | Key field empty. |
| `11-mobile-overview.png` | 390px overview | Same local data as 01. |
| `12-mobile-nav.png` | Open drawer, Overview current | Navigation only. |

These files do not replace `docs/assets/portfolio/*.png` or the LinkedIn set.
No `whsec_`, operator key, or OAuth secret is embedded in the PNGs.
