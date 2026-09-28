import { useCallback, useEffect, useState } from 'react'
import { API_URL, createIntegration, getHealth, listIntegrations } from './api'
import CreateIntegrationForm from './components/CreateIntegrationForm'
import IntegrationsTable from './components/IntegrationsTable'
import SummaryCards from './components/SummaryCards'
import type { Integration, IntegrationProvider } from './types'

function App() {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [systemStatus, setSystemStatus] = useState<'checking' | 'ok' | 'error'>('checking')

  const loadIntegrations = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const [health, items] = await Promise.all([getHealth(), listIntegrations()])
      setSystemStatus(health.status === 'ok' ? 'ok' : 'error')
      setIntegrations(items)
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
    await createIntegration({ name, provider })
    await loadIntegrations()
  }

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
