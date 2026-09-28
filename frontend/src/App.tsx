import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  API_URL,
  createIntegration,
  getHealth,
  listIntegrations,
  listProviderRequests,
} from './api'
import CreateIntegrationForm from './components/CreateIntegrationForm'
import FailureLabPanel from './components/FailureLabPanel'
import GitHubConnectionPanel from './components/GitHubConnectionPanel'
import IntegrationsTable from './components/IntegrationsTable'
import ProviderRequestsTable from './components/ProviderRequestsTable'
import StripeWebhooksPanel from './components/StripeWebhooksPanel'
import SummaryCards from './components/SummaryCards'
import type { Integration, IntegrationProvider, ProviderRequestLog } from './types'

function readOauthNotice(): string | null {
  const params = new URLSearchParams(window.location.search)
  if (params.get('oauth') !== 'github') return null
  const status = params.get('status')
  window.history.replaceState({}, '', window.location.pathname)
  if (status === 'connected') return 'GitHub connected successfully.'
  if (status === 'cancelled') return 'GitHub connection was cancelled.'
  if (status === 'error') return 'GitHub authorization did not complete.'
  return null
}

function App() {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [requestLogs, setRequestLogs] = useState<ProviderRequestLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [systemStatus, setSystemStatus] = useState<'checking' | 'ok' | 'error'>('checking')
  const [oauthNotice, setOauthNotice] = useState<string | null>(() => readOauthNotice())

  const loadIntegrations = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const [health, items, logs] = await Promise.all([
        getHealth(),
        listIntegrations(),
        listProviderRequests({ limit: 50 }),
      ])
      setSystemStatus(health.status === 'ok' ? 'ok' : 'error')
      setIntegrations(items)
      setRequestLogs(logs)
    } catch (err) {
      setSystemStatus('error')
      setError(err instanceof Error ? err.message : 'Failed to load integrations.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadIntegrations()
  }, [loadIntegrations])

  async function handleCreate(name: string, provider: IntegrationProvider) {
    const created = await createIntegration({ name, provider })
    setIntegrations((current) => [...current, created])
  }

  const githubIntegrations = useMemo(
    () => integrations.filter((item) => item.provider === 'github'),
    [integrations],
  )

  const noticeIsError = oauthNotice?.includes('cancelled') || oauthNotice?.includes('did not complete')

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Partner integration console</p>
          <h1>IntegrationLab</h1>
        </div>
        <div className="header-meta">
          <div className={`status-chip status-chip-${systemStatus}`}>
            System/foundation status:{' '}
            {systemStatus === 'checking'
              ? 'Checking…'
              : systemStatus === 'ok'
                ? 'OK'
                : 'Unavailable'}
          </div>
          <p className="muted api-url">API: {API_URL}</p>
        </div>
      </header>

      <main className="app-main">
        {oauthNotice ? (
          <div
            className={`banner ${noticeIsError ? 'banner-error' : 'banner-success'}`}
            role="status"
          >
            <strong>{oauthNotice}</strong>
            <button type="button" className="secondary-button" onClick={() => setOauthNotice(null)}>
              Dismiss
            </button>
          </div>
        ) : null}

        {error ? (
          <div className="banner banner-error" role="alert">
            <strong>Could not reach the backend.</strong>
            <p>{error}</p>
            <button type="button" onClick={() => void loadIntegrations()}>
              Retry
            </button>
          </div>
        ) : null}

        {loading ? <p className="loading-text">Loading integrations…</p> : null}

        {!loading && !error ? (
          <>
            <SummaryCards integrations={integrations} />

            <section className="panel">
              <div className="panel-header">
                <h2>Integrations</h2>
                <button type="button" className="secondary-button" onClick={() => void loadIntegrations()}>
                  Refresh
                </button>
              </div>
              <IntegrationsTable integrations={integrations} />
            </section>

            {githubIntegrations.length > 0 ? (
              <section className="panel">
                <h2>GitHub connections</h2>
                <p className="muted">
                  Connect a GitHub OAuth App with read:user scope. Tokens never reach the browser.
                </p>
                <div className="github-list">
                  {githubIntegrations.map((integration) => (
                    <article key={integration.id} className="github-card">
                      <h3>{integration.name}</h3>
                      <GitHubConnectionPanel
                        integration={integration}
                        onStatusChange={loadIntegrations}
                      />
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="panel">
              <h2>Failure Lab</h2>
              <FailureLabPanel integrations={integrations} onCompleted={loadIntegrations} />
            </section>

            <section className="panel">
              <h2>Stripe Webhooks</h2>
              <StripeWebhooksPanel integrations={integrations} />
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>Recent provider requests</h2>
                <button type="button" className="secondary-button" onClick={() => void loadIntegrations()}>
                  Refresh logs
                </button>
              </div>
              <p className="muted">
                Outbound calls IntegrationLab makes to providers. Inbound Stripe webhooks appear in
                the Stripe Webhooks section instead.
              </p>
              <ProviderRequestsTable logs={requestLogs} />
            </section>

            <section className="panel">
              <CreateIntegrationForm onSubmit={handleCreate} disabled={loading} />
            </section>
          </>
        ) : null}
      </main>
    </div>
  )
}

export default App
