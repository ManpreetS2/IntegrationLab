# Database Notes (Interview Study)

IntegrationLab persists integrations, OAuth state/credentials, GitHub profile
metadata, and provider request logs in PostgreSQL.

## ER overview

```text
integrations
  │
  ├── oauth_credentials     (encrypted access token, one per integration)
  ├── oauth_sessions        (temporary state + encrypted PKCE verifier)
  ├── github_profiles       (safe public metadata)
  └── provider_request_logs (outbound HTTP observability)
```

```mermaid
erDiagram
  INTEGRATIONS ||--o| OAUTH_CREDENTIALS : has
  INTEGRATIONS ||--o{ OAUTH_SESSIONS : starts
  INTEGRATIONS ||--o| GITHUB_PROFILES : mirrors
  INTEGRATIONS ||--o{ PROVIDER_REQUEST_LOGS : emits

  INTEGRATIONS {
    uuid id PK
    varchar name
    varchar provider
    varchar status
    timestamptz created_at
    timestamptz last_checked_at
  }

  OAUTH_SESSIONS {
    uuid id PK
    uuid integration_id FK
    varchar provider
    varchar state_hash UK
    text code_verifier_encrypted
    timestamptz created_at
    timestamptz expires_at
    timestamptz used_at
  }

  OAUTH_CREDENTIALS {
    uuid id PK
    uuid integration_id FK UK
    varchar provider
    text access_token_encrypted
    varchar token_type
    text granted_scopes
    timestamptz created_at
    timestamptz updated_at
  }

  GITHUB_PROFILES {
    uuid integration_id PK_FK
    bigint github_user_id
    varchar login
    text avatar_url
    text html_url
    int public_repos
    timestamptz connected_at
    timestamptz last_synced_at
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
  }
```

Deleting an integration cascades to related OAuth sessions, credentials, GitHub
profile, and request logs (`ON DELETE CASCADE`).

## Why credentials and profile are separate

- **Credentials** hold secrets (encrypted tokens). They must never be serialized
  to the frontend.
- **Profiles** hold safe display metadata (login, avatar, public repo count).

Separating them keeps API responses simple and reduces the chance of accidental
token leakage through ORM serialization.

## Encryption at rest

Access tokens and PKCE verifiers are stored as Fernet ciphertext.

- Key source: `TOKEN_ENCRYPTION_KEY` only
- Do not auto-generate a new key on every startup
- Ciphertext is never returned by the API

## Migrations

| Revision | Purpose |
|----------|---------|
| `001_create_integrations` | Base integrations table |
| `002_github_oauth_and_logs` | OAuth + profile + request logs |

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Do not edit `001` after it has been merged. Add new revisions instead.

## Observability tradeoff

Provider request logs are committed independently of the main OAuth persistence
transaction so a logging insert failure does not wipe a successful GitHub call.
Credential/profile updates for a connection still commit atomically together.

## Test database

Pytest uses `integrationlab_test` (name must end with `_test`). Fixtures truncate
all OAuth-related tables between tests and refuse unsafe DB names.

## Related docs

- [architecture.md](architecture.md)
- [github-oauth.md](github-oauth.md)
