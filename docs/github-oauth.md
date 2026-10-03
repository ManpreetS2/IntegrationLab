# GitHub OAuth (IntegrationLab)

This milestone connects IntegrationLab to a **real third-party provider** using
GitHub's OAuth authorization-code flow. It is **provider connection**, not
"Sign in to IntegrationLab with GitHub."

There are still **no application users**, JWTs, or login pages.

## OAuth App vs GitHub App

GitHub currently recommends **GitHub Apps** for many production integrations
because they support finer-grained permissions and better installation/token
models.

IntegrationLab intentionally uses a **GitHub OAuth App** in this milestone to
demonstrate:

- authorization-code flow
- `state` (CSRF protection)
- PKCE (S256)
- redirect / callback behavior
- backend token exchange
- delegated API access with a stored access token

We are **not** converting the project into a GitHub App here.

## Create a GitHub OAuth App (local)

1. Open [GitHub Developer Settings → OAuth Apps](https://github.com/settings/developers).
2. Click **New OAuth App**.
3. For the **full Compose stack** (`make compose-up`, UI on `:8080`) fill in:
   - **Application name:** IntegrationLab Local (or similar)
   - **Homepage URL:** `http://localhost:8080`
   - **Authorization callback URL:** `http://localhost:8080/api/oauth/github/callback`
4. Register the application.
5. Copy the **Client ID**.
6. Generate a **Client secret** and copy it once (GitHub shows it only briefly).

For split local dev (Vite `:5173` + API `:8000`), use homepage `http://localhost:5173`
and callback `http://localhost:8000/api/oauth/github/callback` instead.

Never commit the client secret. Never put it in React or frontend env files.

## Environment variables

In project-root `.env` (Compose) and/or `backend/.env` (copied from `.env.example`):

```bash
GITHUB_CLIENT_ID=your_client_id_here
GITHUB_CLIENT_SECRET=your_client_secret_here
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8080/api/oauth/github/callback
FRONTEND_URL=http://localhost:8080
TOKEN_ENCRYPTION_KEY=your_fernet_key_here
```

Generate a Fernet key (do not print it into chat logs or commit it):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste that value into `TOKEN_ENCRYPTION_KEY` in `backend/.env` only.

Notes:

- The FastAPI app **starts** without GitHub credentials (`/health` still works).
- OAuth start/callback/check return **503** with a safe message if config is missing.
- Do **not** regenerate `TOKEN_ENCRYPTION_KEY` after storing tokens — old ciphertext becomes undecryptable.

## Scope

We request only:

```text
read:user
```

We do **not** request `repo`. This milestone only needs enough access to identify
the authorized GitHub user and prove a real provider connection.

## Endpoints

| Step | Method + path |
|------|----------------|
| Start connect | `GET /api/integrations/{id}/github/connect` |
| Callback | `GET /api/oauth/github/callback` |
| Profile | `GET /api/integrations/{id}/github` |
| Check | `POST /api/integrations/{id}/github/check` |
| Request logs | `GET /api/provider-requests` |

Connect is a **browser navigation** (302 → GitHub). Do not `fetch()` it expecting JSON.

## Flow (plain English)

1. Dashboard **Connect GitHub** sends the browser to the backend start URL.
2. Backend creates an OAuth session (`state` hash + encrypted PKCE verifier) and redirects to GitHub.
3. User approves on GitHub.
4. GitHub redirects to the backend callback with `code` + `state`.
5. Backend validates state (exists, unused, unexpired), decrypts the verifier, exchanges the code for an access token.
6. Backend calls `GET https://api.github.com/user` with the token.
7. Backend stores the **encrypted** token, safe profile metadata, marks the integration `connected`, and redirects to the frontend with `/?oauth=github&status=connected`.
8. React never sees the access token.

Cancel / error callbacks (`?error=access_denied&state=...`) go through the same
state validation. The request is only treated as our flow when `state` is
present, known, for GitHub, unused, and unexpired. In that case the state is
marked used and the browser is redirected to
`/?oauth=github&status=cancelled` (or `status=error` for other errors).
Missing, unknown, expired, or reused state returns HTTP 400.
`error_description` is never reflected back.

## Security checklist

| Rule | How we enforce it |
|------|-------------------|
| Client secret backend-only | Used only in server-side token exchange |
| Access token encrypted at rest | Fernet via `TOKEN_ENCRYPTION_KEY` |
| `state` prevents OAuth CSRF | Random state, hashed in DB, bound to integration |
| PKCE protects code exchange | S256 challenge; original verifier sent on exchange |
| Single-use / expiry | ~10 minute TTL; `used_at` set on success and on valid cancel |
| Tokens never in React | Not in JSON, redirects, or localStorage |
| Minimal scope | `read:user` only |
| `.env` ignored | Secrets stay local |
| Sanitized errors | No token/secret leakage in API errors |
| Request logs exclude secrets | Method/endpoint/status/latency only |

## Manual verification

With real `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and `TOKEN_ENCRYPTION_KEY`:

1. `alembic upgrade head` and start backend + frontend.
2. Create or use a GitHub integration.
3. Click **Connect GitHub** → approve on GitHub → return to dashboard.
4. Confirm avatar, `@login`, public repo count, status `connected`.
5. Click **Check connection** and confirm it succeeds.
6. Confirm **Recent provider requests** shows `/login/oauth/access_token` and `/user`.
7. Restart the backend and confirm the connection still works.

Automated tests mock GitHub with `respx` and do **not** need real credentials.

## Optional: clean old OAuth sessions

Used/expired sessions are already rejected. To delete old rows manually:

```sql
DELETE FROM oauth_sessions
WHERE used_at IS NOT NULL
   OR expires_at < NOW();
```

No background worker in this milestone.

---

## Interview learning notes

### What is OAuth?

OAuth is a **delegation** protocol: a user grants an application limited access to
a provider (GitHub) without sharing their GitHub password with that application.

### Authorization vs authentication?

- **Authentication:** proving who you are (login).
- **Authorization:** granting permission to do something.

This milestone uses OAuth for **authorization to call GitHub APIs** on behalf of
the user who approved the app. It is not IntegrationLab's login system.

### What is an authorization code?

A short-lived one-time code GitHub returns to our callback URL after the user
approves. It is **not** the access token. The backend exchanges it for a token.

### Why is the code temporary?

If intercepted, its usefulness window is tiny, and it usually requires the
client secret (and PKCE verifier) to exchange. It is meant to be consumed once.

### What is an access token?

A credential that authorizes API calls to GitHub (here, `GET /user`) within the
granted scopes until revoked or expired.

### Why does the backend exchange the code?

The exchange needs the **client secret** and must keep the **access token** off
the browser. React never performs token exchange.

### What is `redirect_uri`?

The exact callback URL registered on the OAuth App. GitHub only redirects codes
to registered URIs, which prevents sending codes to attacker-controlled sites.

### What is scope?

The permission set requested. We only ask for `read:user`.

### What is `state`?

A random value the backend generates before redirecting to GitHub and expects
back unchanged on callback.

### What attack does `state` address?

**OAuth CSRF / login CSRF-style attacks:** tricking a victim's browser into
completing an OAuth callback the victim did not initiate, linking the wrong
provider account. Matching `state` proves the callback belongs to our started flow.

### What is PKCE?

Proof Key for Code Exchange. The client creates a high-entropy `code_verifier`,
sends a derived `code_challenge` (S256) on authorize, and must present the
original verifier during token exchange so a stolen code alone is not enough.

### What are `code_verifier` and `code_challenge`?

- `code_verifier`: random secret kept by the backend (encrypted in the OAuth session).
- `code_challenge`: `BASE64URL(SHA256(code_verifier))` sent to GitHub on authorize.

### Why can't the access token live in React / localStorage?

Browser storage is exposed to XSS and extensions. Tokens would also appear in
frontend state and network traces. Backend storage + encryption keeps them off
the client.

### Why encrypt it in PostgreSQL?

Database access (backups, dumps, compromised read access) should not yield usable
plaintext tokens. Fernet provides authenticated encryption at rest.

### OAuth App vs GitHub App?

OAuth Apps issue user-delegated tokens with classical scopes. GitHub Apps can be
installed on orgs/repos with finer permissions and different token issuance.
We use an OAuth App here for learning the classical web flow.

### Why only `read:user`?

Enough to identify the user and show public profile metadata. No private repos,
no writes, no webhook administration.

### How do we know the provider connection is healthy?

**Check connection** decrypts the stored token, calls GitHub `/user`, logs
latency/status, refreshes profile metadata, and updates integration status.
A `401` marks the integration `needs_setup` so the UI can offer reconnect.
