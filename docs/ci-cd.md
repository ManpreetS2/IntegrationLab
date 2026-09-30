# CI/CD

## Separation of concerns

| Workflow | Trigger | Spends AWS money? |
|----------|---------|-------------------|
| `.github/workflows/ci.yml` | `pull_request`, `push` to `main` | No |
| `.github/workflows/deploy.yml` | `workflow_dispatch` only | Yes (when infra exists) |

CI validates code quality. CD deploys only when a human runs it against the
GitHub Environment `production`.

## CI jobs

### backend-tests

- Python 3.13
- PostgreSQL 18 service container
- Dedicated database ending in `_test` (existing guard enforced)
- `alembic upgrade head` then `pytest`
- Fake Fernet / GitHub / Stripe values only

### frontend-quality

- Node 22
- `npm ci` (not `npm install`)
- `npm run lint` then `npm run build` with `VITE_API_URL=""`
- Asserts the production bundle does not hardcode `localhost:8000`

### backend-container

- Builds `backend/Dockerfile` without AWS credentials
- Scans the image tar for `.env`, terraform state, and credential files

### terraform-quality

- Terraform 1.16.4
- `fmt -check`, `init -backend=false`, `validate`
- Never `terraform apply`

## Permissions

CI: `contents: read` only.

Deploy: `contents: read` + `id-token: write` for OIDC. No `write-all`.

## CD sequence

1. Assume IAM role via GitHub OIDC (no static access keys)
2. Build/push ECR image tagged with `${GITHUB_SHA}` (immutable)
3. Render + register a new ECS task definition revision
4. Run one-off migration task (`alembic upgrade head`); abort on failure
5. Deploy service; wait for stability; set desired count
6. Build frontend (same-origin API); sync to S3
7. CloudFront invalidation
8. Smoke tests through CloudFront URL

## Recommended branch protection

Require these checks before merge to `main`:

- `backend-tests`
- `frontend-quality`
- `backend-container`
- `terraform-quality`

Do not modify repository branch protection from automation unless explicitly
requested.

## Dependabot

`.github/dependabot.yml` updates pip, npm, GitHub Actions, and Terraform weekly
with a modest open-PR limit.
