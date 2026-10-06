# External Acceptance Runbook

Executable checklist for proving IntegrationLab against **real** GitHub and
Stripe test-mode infrastructure.

Vocabulary (do not collapse):

| Status | Meaning |
|--------|---------|
| **Implemented** | Code/config exists in the repository |
| **CI verified** | Automated CI exercised it |
| **Locally verified** | Ran successfully on a developer machine (Compose/stack) |
| **Externally verified** | Real provider/cloud interaction completed successfully |

Never mark a claim **Externally verified** unless the provider step actually ran.

---

## 0. Prerequisites

| Item | Expected |
|------|----------|
| `main` SHA baseline | Contains support-operations foundation (PR #14) |
| Docker / Compose | `docker compose version` works |
| Local secrets file | Project-root `.env` and/or `backend/.env` (gitignored) |
| Operator key | `OPERATOR_API_KEY` ≥ 24 chars |
| Token cipher | `TOKEN_ENCRYPTION_KEY` (Fernet) |
| GitHub OAuth App | Client ID + secret |
| Stripe CLI | Installed + `stripe login` (test mode) |

Secret presence only — never paste secret values into docs or chat.

Canonical full-stack entrypoint:

```bash
make compose-up
# Console: http://localhost:8080
# Unlock with OPERATOR_API_KEY from local .env
```

Same-origin browser routes (nginx → backend):

| Purpose | URL |
|---------|-----|
| Console | `http://localhost:8080` |
| Operator probe | `http://localhost:8080/auth/operator` |
| GitHub OAuth callback | `http://localhost:8080/api/oauth/github/callback` |
| Stripe webhook | `http://localhost:8080/webhooks/stripe/{integration_id}` |
| Health | `http://localhost:8080/health` |

Compose injects `GITHUB_*`, `TOKEN_ENCRYPTION_KEY`, and `STRIPE_WEBHOOK_SECRET`
from the project-root `.env` into the backend service.

---

## 1. Stack boot (Locally verified gate)

| Step | Action | Expected | Evidence |
|------|--------|----------|----------|
| 1.1 | `make compose-up` | postgres healthy → migrate → backend healthy → frontend on `:8080` | `docker compose -f docker-compose.full.yml ps` |
| 1.2 | `curl -sS http://localhost:8080/health` | JSON healthy | response body |
| 1.3 | `curl -sS http://localhost:8080/ready` | ready | response body |
| 1.4 | `curl -sS http://localhost:8080/auth/operator` | JSON capability probe (not SPA HTML) | `Content-Type: application/json` |
| 1.5 | Unlock console with operator key | Dashboard loads | screenshot (no key visible) |

Classification after success: **Locally verified** (stack boot).

---

## 2. GitHub OAuth App setup

Create at [GitHub → Developer settings → OAuth Apps](https://github.com/settings/developers).

| Field | Value for Compose acceptance |
|-------|------------------------------|
| Application name | `IntegrationLab Local` |
| Homepage URL | `http://localhost:8080` |
| Authorization callback URL | `http://localhost:8080/api/oauth/github/callback` |

Place into project-root `.env` (and `backend/.env` if used for non-Compose runs):

```bash
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8080/api/oauth/github/callback
FRONTEND_URL=http://localhost:8080
TOKEN_ENCRYPTION_KEY=...   # already generated locally; do not rotate after tokens exist
OPERATOR_API_KEY=...
```

Then recreate the backend container so env is picked up:

```bash
docker compose -f docker-compose.full.yml up -d --force-recreate backend
```

---

## 3. GitHub OAuth happy path

| Step | Action | Expected | Evidence |
|------|--------|----------|----------|
| 3.1 | Create/select GitHub integration (professional name) | Integration row exists, env ≠ production unless intentional | Integrations UI |
| 3.2 | Connect GitHub | Browser redirect to GitHub authorize | audit `github_connect_requested`, actor `browser_handoff` |
| 3.3 | Approve `read:user` | Callback returns to console | connected status |
| 3.4 | Profile shown | Safe login/name/avatar fields only | screenshot |
| 3.5 | Token at rest | Encrypted column only; no plaintext in API/logs/UI | DB spot-check / API responses |
| 3.6 | Connection check / diagnostics | Real `provider_request` with `is_simulated=false` | Requests + Diagnostics |
| 3.7 | Support case | Pin real evidence, note, transition, timeline, audit | Support Cases + Audit |

Classification after success: **Externally verified** (GitHub OAuth + real `/user`).

### Negative path (pick at least one)

| Option | Action | Expected |
|--------|--------|----------|
| A. Deny/cancel | Start connect, deny on GitHub | No credentials; safe redirect; no raw `error_description` leak |
| B. Revoke | Revoke app in GitHub settings → run check | Real auth failure evidence; not “provider globally down”; reconnect works |

---

## 4. Stripe CLI acceptance

| Step | Action | Expected | Evidence |
|------|--------|----------|----------|
| 4.1 | `stripe version` + `stripe login` | CLI authenticated (test mode) | CLI status (no secrets logged) |
| 4.2 | Note Stripe integration UUID from UI/API | UUID for webhook path | Integrations |
| 4.3 | `stripe listen --forward-to http://localhost:8080/webhooks/stripe/<id>` | Forwarding; CLI prints `whsec_...` | — |
| 4.4 | Put signing secret in `.env` as `STRIPE_WEBHOOK_SECRET` and recreate backend | Webhook endpoint accepts signed events | — |
| 4.5 | Trigger supported event (e.g. `payment_intent.succeeded`) | Signature OK; durable receipt | Webhooks UI |
| 4.6 | Operator process | Attempt + effect; `webhook_process_requested` audit before process | Attempts / Audit / correlation |
| 4.7 | Duplicate delivery | Same provider event id → `delivery_count`↑; one effect | Detail view |
| 4.8 | Controlled failure (`object` missing / known permanent path) | Failed/retry semantics | Failed queue |
| 4.9 | Manual retry / dismiss as appropriate | Audit + attempt correlation | Audit |

Classification after success: **Externally verified** (Stripe signed webhook test-mode).

Mark duplicate delivery **Externally verified** only if the second delivery used a legitimate signed redelivery with the same provider event id.

---

## 5. Screenshots (safe)

Directory: `docs/assets/portfolio/`

Capture without secrets, operator key, cookies, or private paths:

1. GitHub connected integration
2. Real provider request (`simulated=false`)
3. Diagnostics run
4. Support case + timeline
5. Audit / correlation
6. Stripe event detail (attempts/effects)
7. Failed/retry queue (if exercised)

---

## 6. After acceptance — docs to update

- [x] `docs/verification.md` — upgrade only proven rows
- [x] README verification section
- [x] `docs/demo-script.md` — use real story
- [x] Portfolio screenshots committed (safe only) — `docs/assets/portfolio/`

AWS `terraform apply` is **out of scope** for this runbook.
