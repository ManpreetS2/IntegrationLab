# IntegrationLab v2 demo script

This is a shot list and narration for a 60–90 second screen recording. It is not a claim that a video file is already in the repository.

Record the local console at http://127.0.0.1:8080. Use Frosted Pearl, then one Graphite Glass cut. Do not open the credential dialog while recording. If a prefix is visible, that is public metadata. Do not show the operator key.

## Sequence

| Time | Picture | Narration |
| --- | --- | --- |
| 0–10s | Overview, light theme | IntegrationLab is a self-hosted console for integration failures. The question is what was stored, and where that evidence came from. |
| 10–25s | Overview health cards, then Integrations | GitHub and Stripe keep their own workflows. Health is calculated from stored evidence. A zero stays neutral. |
| 25–40s | Instrumented application, credential list with the secret hidden, SDK setup | An application registers as Instrumented HTTP. The ingestion credential is shown once and is not the operator key. The Python and Node SDKs are installed from this repo. |
| 40–60s | Telemetry after the local fixture | The sample reports HTTP 200, 429, 500, and a timeout. The page says SDK-reported. IntegrationLab did not call the upstream service. p95 stays unavailable under 20 observations. |
| 60–75s | Failures filtered to SDK-reported, then Stripe webhooks | SDK failures stay on their own source. Stripe deliveries, duplicates, and retries are a separate log. |
| 75–90s | README tests section, or the CI page | Backend, frontend, both SDKs, and the Compose smoke job are in GitHub Actions. AWS Terraform is validated, not deployed. |

## Closing line

The repository is public. The local demo is not a hosted service.
