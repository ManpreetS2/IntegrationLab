# Database Notes

PostgreSQL stores integrations, OAuth artifacts, provider request logs, Failure
Lab runs, Stripe webhook events with their processing history, and persisted
diagnostic runs with their check results.

## ER overview

```text
integrations
  │
  ├── oauth_credentials
  ├── oauth_sessions
  ├── github_profiles
  ├── provider_request_logs   (outbound: real + simulated)
  ├── failure_lab_runs
  ├── webhook_events          (inbound)
  │     ├── webhook_processing_attempts
  │     └── webhook_effects
  └── diagnostic_runs         (operator-triggered)
        └── diagnostic_checks
```

```mermaid
erDiagram
  INTEGRATIONS ||--o| OAUTH_CREDENTIALS : has
  INTEGRATIONS ||--o{ OAUTH_SESSIONS : starts
  INTEGRATIONS ||--o| GITHUB_PROFILES : mirrors
  INTEGRATIONS ||--o{ PROVIDER_REQUEST_LOGS : emits
  INTEGRATIONS ||--o{ FAILURE_LAB_RUNS : experiments
  INTEGRATIONS ||--o{ WEBHOOK_EVENTS : receives
  WEBHOOK_EVENTS ||--o{ WEBHOOK_PROCESSING_ATTEMPTS : "attempted by"
  WEBHOOK_EVENTS ||--o{ WEBHOOK_EFFECTS : produces
  INTEGRATIONS ||--o{ DIAGNOSTIC_RUNS : diagnosed
  DIAGNOSTIC_RUNS ||--|{ DIAGNOSTIC_CHECKS : contains

  DIAGNOSTIC_RUNS {
    uuid id PK
    uuid integration_id FK
    varchar provider
    varchar trigger "manual"
    timestamptz started_at
    timestamptz completed_at "null while running"
    varchar overall_status "running | pass | warning | fail | unknown"
    text summary
  }

  DIAGNOSTIC_CHECKS {
    uuid id PK
    uuid diagnostic_run_id FK
    int position
    varchar check_code "unique with diagnostic_run_id"
    varchar title
    varchar status "pass | warning | fail | unknown"
    boolean required
    text evidence
    text recommendation
    int latency_ms
    timestamptz observed_at
  }

  PROVIDER_REQUEST_LOGS {
    uuid id PK
    uuid integration_id FK
    varchar provider
    varchar method
    varchar endpoint
    int status_code
    int latency_ms
    timestamptz timestamp
    text error_message
    int rate_limit_remaining
    boolean is_simulated
    varchar scenario
  }

  FAILURE_LAB_RUNS {
    uuid id PK
    uuid integration_id FK
    varchar provider
    varchar scenario
    varchar method
    varchar endpoint
    int status_code
    int latency_ms
    varchar error_code
    varchar diagnosis_code
    boolean retryable
    timestamptz created_at
  }

  WEBHOOK_EVENTS {
    uuid id PK
    uuid integration_id FK
    varchar provider
    varchar provider_event_id "unique with integration_id, provider"
    varchar event_type
    varchar provider_object_id
    varchar api_version
    boolean livemode
    timestamptz provider_created_at
    bigint amount
    varchar currency
    varchar processing_status
    int delivery_count
    int attempt_count
    int cycle_attempt_count
    int retry_cycle
    int manual_retry_count
    int max_attempts
    timestamptz next_attempt_at
    timestamptz processing_started_at
    timestamptz first_received_at
    timestamptz last_received_at
    timestamptz processed_at
    timestamptz failed_at
    timestamptz dismissed_at
    varchar last_error_code
    text last_error_message
  }

  WEBHOOK_PROCESSING_ATTEMPTS {
    uuid id PK
    uuid webhook_event_id FK
    int attempt_number "unique with webhook_event_id"
    int retry_cycle
    int cycle_attempt_number
    timestamptz started_at
    timestamptz finished_at
    varchar outcome
    varchar error_code
    text error_message
    boolean retryable
    int scheduled_delay_seconds
    boolean manual
  }

  WEBHOOK_EFFECTS {
    uuid id PK
    uuid webhook_event_id FK
    varchar effect_key "unique with webhook_event_id"
    varchar effect_type
    varchar provider_object_id
    text summary
    timestamptz applied_at
  }
```

## Webhook tables

### `webhook_events`

One row per **logical** Stripe event per integration, holding only safe
normalized metadata. There is no raw body column, and no customer or payment
method data.

- `uq_webhook_events_integration_provider_event (integration_id, provider, provider_event_id)`:
  delivery dedupe. Receipt uses `INSERT … ON CONFLICT DO NOTHING`; on conflict
  it atomically increments `delivery_count` and updates `last_received_at`.
- `attempt_count` counts attempts across all cycles. `cycle_attempt_count` is
  checked against `max_attempts` (4) and resets on manual retry, when
  `retry_cycle` is incremented.
- Index `(processing_status, next_attempt_at)` serves the due-event query;
  `first_received_at` serves newest-first listing.

### `webhook_processing_attempts`

Append-only processing history, one row per attempt:
`in_progress → succeeded | ignored | failed | abandoned`. It records
`scheduled_delay_seconds` for retries and `manual` for operator-triggered
attempts. `uq_webhook_attempts_event_attempt_number` prevents two attempts from
claiming the same number. Manual retry and dismiss never delete rows.

### `webhook_effects`

Internal side effects (`payment_success_recorded`, `payment_failure_recorded`,
`refund_recorded`). `uq_webhook_effects_event_effect_key` plus
`ON CONFLICT DO NOTHING` makes each effect apply at most once, even across
redelivery, reprocessing, crashes, or manual retries. The effect insert and the
`processed` status change commit together.

All child tables use `ON DELETE CASCADE` from their parent.

## Diagnostic tables

### Run/check relationship

A `diagnostic_runs` row is one operator click on *Run diagnostics*. It owns an
ordered set of `diagnostic_checks` rows, one per check, ordered by `position`.
`uq_diagnostic_checks_run_check_code` means a run records each check at most
once. The run's `overall_status` and `summary` are derived from its checks
when the run completes:

- a failed required check makes the run `fail`;
- otherwise any warning makes it `warning`;
- otherwise any unknown makes it `unknown`;
- otherwise it is `pass`.

The run is inserted and committed as `running` **before** any check executes.
That row doubles as a lock: another run for the same integration returns 409
until the first completes or is older than 120 seconds. Deleting an integration
cascades to its runs, and deleting a run cascades to its checks.

Indexes serve exactly the queries the app makes:

- `(integration_id, started_at)`: per-integration history and "latest run";
- `started_at`: the window counts and the failures feed;
- `diagnostic_run_id`: loading a run's checks.

### Why results are persisted

- **History:** "it passed yesterday, it fails today" is itself evidence.
- **Auditability:** the exact evidence an operator acted on can be reopened
  later, instead of re-running and getting a different answer.
- **Dashboard input:** the latest run appears on each health card, and failed
  runs appear in the failures feed, without calling any provider again.

### Why provider secrets are NOT persisted

Check rows hold only human-readable evidence and recommendations. For example,
"An encrypted OAuth credential is stored (value not displayed)" or "Missing
configuration: GITHUB_CLIENT_SECRET". They never hold:

- tokens or ciphertext;
- `STRIPE_WEBHOOK_SECRET`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, or
  `DATABASE_URL`;
- signature headers, `Authorization` headers, or raw provider bodies.

Diagnostic history is read by the UI and kept indefinitely, so anything stored
there would effectively be published. Tests scan both the API responses and the
stored rows for these values.

## Why simulated vs real logs must be distinguishable

Failure Lab writes provider request logs so the dashboard can show latency and
status evidence. Without `is_simulated` (and `scenario`), a simulated 401 would
look identical to a real GitHub 401 and could mislead operators.

UI badges:

- **Real**: outbound GitHub traffic
- **Simulated**: a Failure Lab experiment

## Migrations

| Revision | Purpose |
|----------|---------|
| `001_create_integrations` | Base integrations |
| `002_github_oauth_and_logs` | OAuth + profiles + request logs |
| `003_failure_lab` | `is_simulated`/`scenario` + `failure_lab_runs` |
| `004_stripe_webhooks` | `webhook_events`, `webhook_processing_attempts`, `webhook_effects` |
| `005_diagnostics` | `diagnostic_runs`, `diagnostic_checks` |

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Do not edit 001–004 after merge. No data retention policy is implemented yet:
request logs, webhook history, and diagnostic runs grow until pruned manually.

## Encryption

Access tokens remain Fernet-encrypted. Failure Lab never decrypts them. The
Stripe webhook secret is read from the environment only and is never stored in
the database.

## Test database

Pytest uses `integrationlab_test` (the name must end with `_test`). Between
tests it truncates all application tables, including the webhook and diagnostic
tables.
