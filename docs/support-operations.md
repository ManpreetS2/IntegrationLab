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

### `acknowledged_at` (Phase 1)

Phase 1 cases are created manually by the operator. There is no separate
acknowledgement workflow or status. On create:

`acknowledged_at = opened_at`

A later support-metrics phase can introduce a richer acknowledgement model if needed.

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

## Case numbers

Human-readable identifiers (`CASE-00001`, …) are allocated from the PostgreSQL
sequence `support_case_number_seq`. Gaps are allowed. Numbers are unique and
race-safe — never derived from `COUNT(*)` or `MAX(case_number) + 1`.

## Correlation IDs

- UUID-based (`X-Correlation-ID` accepted only when a valid UUID)
- Bound with a ContextVar for nested service/repository writes
- Stored on support cases, audit events, and durable evidence rows where applicable
- Operator webhook process/retry/dismiss and Failure Lab / diagnostics establish a scope so attempts/runs inherit the same ID
- Safe to show/copy in the UI (`corr_xxxx…` short form)

No OpenTelemetry / Jaeger / Tempo yet.

## Operator audit

Append-only `operator_audit_events` for meaningful ACTIONS:

- integration create/update
- GitHub connect requested (`actor_type=browser_handoff` — public OAuth handoff)
- Failure Lab run, diagnostic run
- webhook process / process-due / retry / dismiss
- support case create/status/severity, notes, evidence pin/unpin

Rules:

- Default actor is `operator` (single-operator truthfulness)
- Metadata is allowlisted (ids/enums/counts only — **no free-form title/name/note text**)
- `safe_summary` is structural (case number, short entity id, scenario enum, status)
- Secrets, tokens, Authorization headers, raw webhook bodies are never stored
- Ordinary GETs do not write audit rows

### Transaction boundaries

| Operation | Boundary |
|-----------|----------|
| Integration create/update | Domain row + audit in **one** commit |
| Failure Lab run | Simulated request log + run + audit in the **success** commit |
| Diagnostics | In-flight "running" row commits first (lock). Completion checks + audit share the **final** commit |
| Webhook retry/dismiss | Status change + audit in one commit |
| Webhook process / process-due | **Intent audit committed first** (`*_requested`); processor keeps its own multi-transaction design; attempts inherit ContextVar correlation |
| GitHub connect | Best-effort `github_connect_requested` when integration exists (`browser_handoff`); audit failure must not block OAuth redirect |

## Evidence pinning

`support_case_evidence` stores a reference:

- evidence_type + evidence_id
- safe_label
- is_simulated
- correlation_id

Supported types today:

- provider_request — **must** belong to the case integration (null `integration_id` rejected)
- webhook_event / webhook_attempt / diagnostic_run / failure_lab_run — same integration
- audit_event — same integration, **or** unscoped audit already tied to this `support_case_id`

Cross-integration pins are rejected. Failure Lab pins remain labeled simulated.

Create-case source evidence requires **both** `source_evidence_type` and `source_evidence_id`, or neither (422 otherwise).

## Timeline

Derived (not a giant copy table) from:

- case history (operator actions at their own timestamps — including pin/unpin)
- notes
- linked evidence rows sorted by **underlying `occurred_at`**, with `pinned_at` exposed separately

So a provider failure at 10:01 that is pinned at 10:15 appears at 10:01 as linked evidence; the history entry records the pin action at 10:15.

## Simulated vs real

Simulated Failure Lab evidence may be attached intentionally for training/demo cases, but:

- must remain visually labeled
- must not drive live integration health
- must not be presented as confirmed production customer impact

## Limitations

- Single-operator auth only (no multi-user RBAC)
- No Stripe reconciliation, provider status, batch recovery, SLOs, or paging integrations yet
- Timeline aggregation is case-scoped; global incident search is future work
