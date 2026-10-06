# Portfolio screenshots

Safe visual evidence for README / demos.

## Rules

- No operator API keys, OAuth secrets, Stripe `whsec_`, tokens, cookies, or local absolute paths
- Prefer professional demo names (`GitHub Developer Integration`, `Stripe Billing Sandbox`)
- Keep **SIMULATED** labels visible on Failure Lab evidence
- Prefer `local` / `test` environment badges — do not imply production customer data

## Expected set

| File | Subject |
|------|---------|
| `01-overview.png` | Reliability overview |
| `02-github-connected.png` | Connected GitHub integration + safe profile metadata |
| `03-real-provider-request.png` | Real (non-simulated) provider request |
| `04-diagnostics.png` | Guided diagnostics |
| `05-support-case.png` | Support case detail |
| `06-case-timeline.png` | Case timeline (evidence, pins, notes, status) |
| `07-audit.png` | Operator audit |
| `08-stripe-webhook.png` | Stripe event detail (deliveries / attempts / effect) |
| `09-stripe-failed-queue.png` | Failed queue + `webhook_invalid_event_data` |

Screenshots committed after the Oct 2026 external-acceptance run (Compose on
`:8080`). Safe UI only — no operator keys, OAuth secrets, or `whsec_` values.
