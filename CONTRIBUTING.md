# Contributing to IntegrationLab

Thanks for taking an interest in IntegrationLab. This is a **single-operator, self-hosted portfolio project** for learning, reproducing, and investigating GitHub API and Stripe test-mode webhook failure modes—not a production integration gateway or hosted service.

**The current Ledger UI v3 portfolio scope is intentionally feature-complete.** Documentation fixes, clear bug reports, reproducible security issues, test regressions, and small correctness improvements are welcome. Please discuss larger feature ideas in an issue first; the deferred roadmap is in [docs/phase-2-backlog.md](docs/phase-2-backlog.md). A request or issue does not mean a new implementation phase is planned.

## Run the demo without provider credentials

Requirements: Git, Make, Python 3, and Docker with Compose. The commands use a macOS/Linux shell; on Windows, use WSL2 with Docker integration.

```bash
git clone https://github.com/ManpreetS2/IntegrationLab.git
cd IntegrationLab
export OPERATOR_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
make demo
```

Open http://localhost:8080 and unlock using the operator key from your shell. `make demo` creates local integrations and **SIMULATED** Failure Lab data. It does not authorize GitHub, invoke Stripe, or create a hosted deployment.

**Stop and keep the PostgreSQL volume:**

```bash
docker compose -f docker-compose.full.yml down
```

**Reset and delete the local Compose database volume:** `make compose-down` (irreversible for that local demo volume).

For real GitHub OAuth / Stripe **test-mode** acceptance, use [docs/external-acceptance.md](docs/external-acceptance.md) and supply your *own* provider credentials. Do not include credentials in bug reports.

## Report a problem

Use a GitHub issue for non-sensitive bugs. Include:

- The expected result and the actual result.
- Exact reproduction steps and whether you ran the simulated demo, real GitHub OAuth, or Stripe test-mode webhooks.
- Your platform, Python/Docker versions, and the relevant command.
- Redacted logs, screenshots, HTTP status codes, and error classifications where available.
- Whether the problem happens on the repository's current `main` branch.

**Security vulnerabilities should not be reported in public issues.** See [SECURITY.md](SECURITY.md).

## Propose a change

1. Open or reference an issue describing the specific problem or documentation gap.
2. Create a small, scoped branch based on current `main`.
3. Keep provider-vs-simulation claims accurate. Do not present test fixtures as actual customer traffic or claim an AWS deployment.
4. Add regression coverage where behavior changes and update docs when setup or external acceptance changes.
5. Open a pull request summarizing the change, reproduction, evidence, and remaining limitations.

### Checks

For a normal local demo, `make demo` is sufficient. If you are modifying code, the repository's CI runs the full verification suite against PostgreSQL, including backend tests, frontend checks, container builds, full-stack smoke, and Terraform validation.

With all development dependencies installed, you can run:

```bash
make verify        # Python tests, frontend lint/tests/build, Terraform validate
make full-verify   # Above + assembled Compose smoke (removes its temporary volume)
```

The full verification commands require additional development tools beyond the Docker-only demo (Python backend dependencies, Node/npm, and Terraform). The repository CI is the authoritative check for these jobs.

## Security, data, and licensing

- Never commit `.env` files, OAuth tokens, signing secrets, encryption keys, operator keys, Terraform state, or unredacted customer data.
- Use local/test provider accounts and clearly label synthetic failure evidence.
- Do not broaden public endpoints or bypass operator authorization to simplify a demo.
- Keep third-party dependencies and assets subject to their own licenses.
- By submitting code you own to this repository, you agree that it can be distributed under the project's [MIT License](LICENSE); only submit content you have the rights to contribute.

For details, see the [architecture](docs/architecture.md), [threat model](docs/threat-model.md), and [claim-to-evidence matrix](docs/verification.md).
