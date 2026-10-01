# Support Operations Foundation

IntegrationLab support cases turn reliability evidence into an operator investigation workflow.

This is a **portfolio / single-operator** model — not a multi-tenant ticketing product and not a company-wide SLA system.

## What a Support Case is

A Support Case is a first-class operational investigation:

- tied to one integration and environment
- has severity + lifecycle status
- pins durable evidence by reference
- records operator notes and status history
- exposes a derived chronological timeline

It is **not** another log row.

## Lifecycle

Statuses:

- `investigating`
- `identified`
- `monitoring`
- `resolved`
- `reopened`

Transitions are validated in the service layer. Invalid jumps return HTTP 400. History events are written for status/severity changes, evidence pin/unpin, and case open.

## Severity

| Level | Meaning in IntegrationLab |
|-------|---------------------------|
| SEV1 | Critical capability unavailable / major business impact |
| SEV2 | Serious degradation or important workflow failing |
| SEV3 | Limited impact / partial failure |
| SEV4 | Low-impact support or configuration investigation |

Severity is manual. A 500 does not auto-promote to SEV1.

## Environments

Integrations and cases carry an explicit environment:

`local` · `test` · `staging` · `production`

Existing rows migrate to `local`. Simulated/demo evidence must not be treated as production impact.

## Correlation IDs

- UUID-based (`X-Correlation-ID` accepted only when a valid UUID)
- Bound with a ContextVar for nested service/repository writes
- Stored on support cases, audit events, and durable evidence rows where applicable
- Safe to show/copy in the UI (`corr_xxxx…` short form)

No OpenTelemetry / Jaeger / Tempo yet.

## Operator audit

Append-only `operator_audit_events` for meaningful ACTIONS (create/update case, pin evidence, Failure Lab run, diagnostics, integration create/update).

- Actor is `operator` (single-operator truthfulness)
- Metadata is allowlisted
- Secrets, tokens, Authorization headers, raw webhook bodies are never stored
- Ordinary GETs do not write audit rows

## Evidence pinning

`support_case_evidence` stores a reference:

- evidence_type + evidence_id
- safe_label
- is_simulated
- correlation_id

Supported types today:

- provider_request
- webhook_event
- webhook_attempt
- diagnostic_run
- failure_lab_run
- audit_event

Cross-integration pins are rejected. Failure Lab pins remain labeled simulated.

## Timeline

Derived (not a giant copy table) from:

- case history
- notes
- pinned evidence events

Each item includes timestamp, type, title, summary, optional source reference, correlation id, and simulated flag.

## Simulated vs real

Simulated Failure Lab evidence may be attached intentionally for training/demo cases, but:

- must remain visually labeled
- must not drive live integration health
- must not be presented as confirmed production customer impact

## Limitations

- Single-operator auth only (no multi-user RBAC)
- No Stripe reconciliation, provider status, batch recovery, SLOs, or paging integrations yet
- Timeline aggregation is case-scoped; global incident search is future work
