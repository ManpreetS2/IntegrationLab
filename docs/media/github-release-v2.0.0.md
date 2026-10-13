# IntegrationLab v2.0.0

Draft release notes. Not published.

IntegrationLab v2 is a self-hosted reliability console. Applications report sanitized HTTP outcomes through the Python and Node SDKs in this repository. Those observations are labeled SDK-reported. IntegrationLab does not call the upstream service to confirm them.

GitHub OAuth and Stripe webhooks keep their own workflows: signed deliveries, duplicate handling, retries, Failure Lab, diagnostics, and support cases. Health, error rate, and p95 follow the stored-evidence rules. p95 stays unavailable below 20 observations. An empty window is not shown as healthy.

The light and dark appearance are Frosted Pearl and Graphite Glass.

The local demonstration is `docs/media/integrationlab-v2-demo.mp4`. A shorter cut is `docs/media/integrationlab-v2-teaser.mp4`. Both were recorded from a local console. The sample fixture produced HTTP 200, 429, 500, and a timeout. Stripe rows in that recording are locally signed test-mode events, not a live Stripe account.

AWS Terraform is validated in CI and has not been applied. The SDK packages are not published to PyPI or npm.

License: MIT.
