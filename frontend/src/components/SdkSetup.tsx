import { apiOrigin } from '../api'
import type { Environment } from '../types'

function SdkSetup({
  integrationId,
  environment,
}: {
  integrationId: string
  environment: Environment
}) {
  const origin = apiOrigin() || 'http://127.0.0.1:8000'
  const envBlock = [
    `export INTEGRATIONLAB_BASE_URL=${origin}`,
    `export INTEGRATIONLAB_INTEGRATION_ID=${integrationId}`,
    'export INTEGRATIONLAB_INGESTION_CREDENTIAL=<paste the one-time credential>',
    `export INTEGRATIONLAB_ENVIRONMENT=${environment}`,
  ].join('\n')

  return (
    <div className="sdk-setup">
      <p className="lg-section-label">SDK setup</p>
      <p className="lg-note">
        Install the SDK in the application that makes the HTTP calls. Do not put the ingestion
        credential in this browser, a frontend bundle, or the telemetry ingestion request from here.
      </p>
      <h4>Python</h4>
      <pre>
        <code>{`python -m pip install -e sdk/python\n${envBlock}`}</code>
      </pre>
      <pre>
        <code>{`from integrationlab import IntegrationLabClient

with IntegrationLabClient.from_env() as lab:
    with lab.observe(service="orders-api", method="GET", route_template="/v1/orders/{id}") as obs:
        response = call_your_client()
        obs.set_status(response.status_code)
    lab.flush()`}</code>
      </pre>
      <h4>Node</h4>
      <pre>
        <code>{`cd sdk/typescript && npm install && npm run build\n${envBlock}`}</code>
      </pre>
      <pre>
        <code>{`import { IntegrationLabClient } from "@integrationlab/sdk";

const lab = IntegrationLabClient.fromEnv();
const fetchObserved = lab.instrumentFetch(fetch, {
  service: "orders-api",
  routeTemplate: "/v1/orders/{id}",
});
const response = await fetchObserved("https://upstream.example/v1/orders/123");
await lab.close();`}</code>
      </pre>
    </div>
  )
}

export default SdkSetup
