# ADR — Support cases + derived incident timeline

## Status

Accepted (2026-10-01)

## Context

IntegrationLab already stores durable reliability evidence (provider requests, webhooks, diagnostics, Failure Lab). Operators still lacked a first-class investigation object that can group evidence, track status, and preserve what the operator did.

Full distributed tracing (OpenTelemetry + Jaeger/Tempo) would be disproportionate for this stage.

## Decision

1. Introduce **Support Cases** as first-class rows with validated lifecycle, severity, and environment.
2. **Pin evidence by reference** instead of copying entire underlying rows.
3. **Derive the case timeline** from case history + notes + linked evidence (plus optional future sources), rather than maintaining a duplicated timeline table. Operator pin actions keep history timestamps; linked evidence sorts by underlying ``occurred_at`` with ``pinned_at`` exposed separately.
4. Use **UUID correlation IDs** with a ContextVar scope before adopting OpenTelemetry.
5. Allocate case numbers from a PostgreSQL sequence (race-safe; gaps allowed).

## Consequences

- Cases remain lightweight and queryable while evidence stays in domain tables.
- Partial timeline composition must be kept consistent in one service (`SupportCaseService.build_timeline`).
- Correlation connects operator actions to evidence without a tracing backend.
- Simulated evidence can be pinned but must remain explicitly labeled.

## Alternatives considered

- Ticket-only metadata without evidence pins — too weak for diagnosis.
- Copying every evidence row into a case timeline table — storage duplication and sync risk.
- Immediate OpenTelemetry adoption — high infra cost for current single-operator scope.
