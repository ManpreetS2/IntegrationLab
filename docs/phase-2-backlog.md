# Phase 2 Backlog — Future / not implemented

These items are **intentionally not built** in IntegrationLab v1.

Do not describe them as existing product features in the README or demos.

| Priority | Item | Why later |
|----------|------|-----------|
| 1 | Stripe missed-event reconciliation / Events API backfill | Needs live/test API key guardrails + cursor/pagination design |
| 2 | Webhook endpoint / configuration drift detection | Requires remote Stripe endpoint inventory vs local routes |
| 3 | GitHub rate-limit intelligence | Build on existing request evidence + headers |
| 4 | Provider-status correlation | External status pages + blast-radius UX |
| 5 | “What changed?” deploy/config overlay | Deploy markers + config diffs |
| 6 | Preflight checker | Opinionated go-live checklist across providers |
| 7 | Redacted support bundle export | Safe packaging of case/timeline/evidence |
| 8 | Dry-run recovery | Preview effects before mutating |
| 9 | Issue grouping | Cluster related failures into cases automatically |
| 10 | Support metrics / SEV analytics | Depends on richer acknowledgement + ownership data |

Also deferred: CloudWatch alarms/synthetics, WAF/rate limiting, multi-tenant RBAC,
Slack/PagerDuty, Redis/Kafka/Celery workers, Kubernetes, AI diagnosis, additional
providers.
