# Security Policy

IntegrationLab is a **local/self-hosted, single-operator portfolio application**, not a multi-user production service or a security-certified payment product.

## Supported scope

Security and correctness reports relevant to the current `main` branch are welcome. The project documents intentional limitations, including:

- A single-operator bearer key instead of per-user identity or RBAC.
- No default WAF or application rate limiting.
- A process-wide Stripe webhook signing secret in v1.
- Operator/CLI-triggered webhook processing rather than a continuously running worker.
- Terraform AWS architecture that is **not deployed**.

These tradeoffs are explained in [docs/threat-model.md](docs/threat-model.md); they should not be interpreted as guarantees that public production deployment is safe.

## Reporting a vulnerability

**Do not create a public GitHub issue containing an exploit, sensitive logs, secret values, or attack instructions.**

Where available, use this repository's GitHub **Security → Report a vulnerability** option to send a private report. If private vulnerability reporting is not enabled, please establish a private communication channel with the repository maintainer before sharing sensitive details. A public issue may be appropriate for non-sensitive security documentation or questions, but not exploit details.

A useful private report includes the affected commit/version, clear reproduction steps, impact, and a proposed mitigation if known. Use non-production credentials and redact tokens, webhook payloads, and personal data.

No response-time, patch-time, or security-service-level commitment is promised for this portfolio project.

## Running safely

- Start with the simulated local demo; it needs no GitHub or Stripe credentials.
- Generate a private `OPERATOR_API_KEY` before configuring real provider secrets.
- Bind local Compose ports to loopback, as configured in `docker-compose.full.yml`; do not expose the demo publicly.
- Keep `.env`, GitHub OAuth tokens, Stripe signing secrets, Fernet keys, database credentials, and Terraform state out of commits, support bundles, screenshots, and issue reports.
- Limit Stripe testing to test mode, and verify signatures using the raw request body.
- Before any internet-facing deployment, perform an environment-specific security review and address the documented authentication, rate-limiting, network/TLS, and credential-lifecycle gaps.
- Treat Terraform validation as static evidence, **not** proof of a live or secure AWS deployment.

See also [docs/external-acceptance.md](docs/external-acceptance.md) and [docs/verification.md](docs/verification.md).
