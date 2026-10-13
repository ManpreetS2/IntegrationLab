import { useMemo } from 'react'
import { apiOrigin, getReliabilityOverview } from '../api'
import CreateIntegrationForm from '../components/CreateIntegrationForm'
import InstrumentedApps from '../components/InstrumentedApps'
import GitHubConnectionPanel from '../components/GitHubConnectionPanel'
import IntegrationsTable from '../components/IntegrationsTable'
import SectionStatus from '../components/SectionStatus'
import SummaryCards from '../components/SummaryCards'
import { useResource, type Resource } from '../hooks'
import type { Environment, Integration, IntegrationProvider } from '../types'

interface IntegrationsPageProps {
  integrations: Resource<Integration[]>
  onCreate: (name: string, provider: IntegrationProvider, environment?: Environment) => Promise<void>
}

function loadOverview() {
  return getReliabilityOverview(24)
}

function IntegrationsPage({ integrations, onCreate }: IntegrationsPageProps) {
  const items = useMemo(() => integrations.data ?? [], [integrations.data])
  const github = items.filter((item) => item.provider === 'github')
  const stripe = items.filter((item) => item.provider === 'stripe')
  const instrumented = items.filter((item) => item.provider === 'instrumented_http')
  const overview = useResource(loadOverview)
  const verification = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const health of overview.data?.integrations ?? []) {
      if (health.webhook_metrics) map.set(health.integration_id, health.webhook_metrics.verification_configured)
    }
    return map
  }, [overview.data])

  function verificationText(id: string): string {
    const configured = verification.get(id)
    if (configured === undefined) return overview.error ? 'Unavailable' : 'Checking…'
    return configured ? 'Configured' : 'Not configured'
  }

  return (
    <>
      <SectionStatus
        loading={integrations.loading}
        error={integrations.error}
        hasData={Boolean(integrations.data)}
        onRetry={integrations.reload}
        loadingText="Loading integrations…"
      />

      {integrations.data ? (
        <>
          <SummaryCards integrations={items} />
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Configured integrations</h2>
                <p className="muted small-text">Provider identity and connection state for this operator console.</p>
              </div>
              <button type="button" className="secondary-button" onClick={integrations.reload}>
                Refresh
              </button>
            </div>
            <IntegrationsTable integrations={items} />
          </section>

          {github.length > 0 ? (
            <section className="panel">
              <h2>GitHub connections</h2>
              <p className="muted">
                Connect a GitHub OAuth App with read:user scope. Tokens never reach the browser.
              </p>
              <div className="github-list">
                {github.map((integration) => (
                  <article key={integration.id} className="github-card">
                    <h3>{integration.name}</h3>
                    <GitHubConnectionPanel integration={integration} onStatusChange={integrations.reload} />
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <InstrumentedApps integrations={instrumented} onChanged={integrations.reload} />

          {stripe.length > 0 ? (
            <section className="panel">
              <h2>Stripe webhook endpoints</h2>
              <p className="muted">
                Point Stripe (or <code>stripe listen --forward-to</code>) at these URLs. The signing
                secret lives only in the backend environment and is never shown here.
              </p>
              <div className="github-list">
                {stripe.map((integration) => (
                  <article key={integration.id} className="github-card">
                    <h3>{integration.name}</h3>
                    <p className="webhook-endpoints">
                      Endpoint: <code>{`${apiOrigin()}/webhooks/stripe/${integration.id}`}</code>
                    </p>
                    <p>
                      Webhook verification: <strong>{verificationText(integration.id)}</strong>
                    </p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}

      <section className="panel">
        <CreateIntegrationForm onSubmit={onCreate} disabled={integrations.loading && !integrations.data} />
      </section>
    </>
  )
}

export default IntegrationsPage
