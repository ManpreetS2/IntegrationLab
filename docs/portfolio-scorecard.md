# Portfolio scorecard — IntegrationLab

Evaluated 2026-10-15 against current `main` baseline `954ed09` + acceptance on `feat/final-portfolio-polish`.

| Area | Evidence | Likely interview question | Strength |
| --- | --- | --- | --- |
| Backend | FastAPI services, repositories, 367 pytest | “How do you structure side effects vs HTTP?” | Strong |
| Frontend | Ledger UI v3 React/TS, lint+30 unit+build | “How do you keep health honest in the UI?” | Strong |
| Database | Alembic through `007`, outage→503 | “What happens when Postgres dies?” | Strong |
| OAuth | State+PKCE+encrypted tokens; external authorize blocked this run | “Walk me through your OAuth threat model.” | Strong design; partial external |
| Security | Operator gate, secret audits, no tokens in UI | “Where do secrets live?” | Strong |
| Distributed systems | Webhook dedupe, retries, idempotent effects | “At-least-once delivery—how do you not double-charge?” | Strong |
| Reliability | Health evaluator, unknown vs healthy | “Why isn’t empty data ‘healthy’?” | Strong |
| Observability | Request logs, telemetry, diagnostics | “What do you measure vs infer?” | Strong |
| Webhooks | Stripe CLI external + recovery demo | “Delivery failure vs processing failure?” | Strongest story |
| SDK design | Python+Node sanitization + credential lifecycle | “Why isn’t SDK data ‘verified’?” | Strong |
| Cloud architecture | Terraform validated; not applied | “Would you ship this to AWS tomorrow?” | Honest architecture |
| CI/CD | Six-job Actions green | “What does CI prove vs not prove?” | Strong |
| Testing | Unit + smoke + external Stripe | “What’s your test pyramid?” | Strong |
| Support workflows | Cases, pins, notes, audit | “How do humans finish the loop?” | Strong |
| Communication | Claim→evidence matrix, limitations | “What must you not overclaim?” | Strong |

## Bottom line

Internship-ready portfolio with a **best-in-class webhook recovery narrative**. Treat GitHub external OAuth as a follow-up interactive demo, not a silent claim.
