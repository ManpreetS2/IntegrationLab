import { useCallback, useEffect, useState } from 'react'
import { ApiError, createIntegration, getReliabilitySystem, listIntegrations } from './api'
import AppShell from './components/AppShell'
import SectionStatus from './components/SectionStatus'
import StripeWebhooksPanel from './components/StripeWebhooksPanel'
import { pageHref, useHashRoute, useResource } from './hooks'
import AuditPage from './pages/AuditPage'
import DiagnosticsPage from './pages/DiagnosticsPage'
import FailuresPage from './pages/FailuresPage'
import IntegrationsPage from './pages/IntegrationsPage'
import OverviewPage from './pages/OverviewPage'
import RequestsPage from './pages/RequestsPage'
import SupportCasesPage from './pages/SupportCasesPage'
import TelemetryPage from './pages/TelemetryPage'
import type { Environment, IntegrationProvider } from './types'

const SYSTEM_POLL_MS = 30_000

function readOauthNotice(): string | null {
  const params = new URLSearchParams(window.location.search)
  if (params.get('oauth') !== 'github') return null
  const status = params.get('status')
  window.history.replaceState({}, '', `${window.location.pathname}${pageHref('integrations')}`)
  if (status === 'connected') return 'GitHub connected successfully.'
  if (status === 'cancelled') return 'GitHub connection was cancelled.'
  if (status === 'error') return 'GitHub authorization did not complete.'
  return null
}

function DatabaseIndicator() {
  const system = useResource(getReliabilitySystem)
  const reload = system.reload

  useEffect(() => {
    const timer = window.setInterval(reload, SYSTEM_POLL_MS)
    return () => window.clearInterval(timer)
  }, [reload])

  let tone: 'checking' | 'ok' | 'error' = 'checking'
  let label = 'Checking…'
  if (system.error) {
    tone = 'error'
    label = system.error instanceof ApiError && system.error.status === 503 ? 'Database unavailable' : 'API unreachable'
  } else if (system.data) {
    tone = system.data.database === 'healthy' ? 'ok' : 'error'
    label = system.data.database === 'healthy' ? 'Database reachable' : 'Database unavailable'
  }
  return (
    <div className={`status-chip status-chip-${tone}`} role="status">
      <span className={`status-dot status-dot-${tone}`} aria-hidden="true" />
      {label}
    </div>
  )
}

function App() {
  const route = useHashRoute()
  const integrations = useResource(listIntegrations)
  const [oauthNotice, setOauthNotice] = useState<string | null>(() => readOauthNotice())
  const reloadIntegrations = integrations.reload

  const handleCreate = useCallback(
    async (name: string, provider: IntegrationProvider, environment?: Environment) => {
      await createIntegration({ name, provider, environment })
      reloadIntegrations()
    },
    [reloadIntegrations],
  )

  const items = integrations.data ?? []
  const noticeIsError = oauthNotice?.includes('cancelled') || oauthNotice?.includes('did not complete')
  const needsIntegrations = route.page !== 'overview' && route.page !== 'integrations'

  return (
    <AppShell page={route.page} connectivity={<DatabaseIndicator />}>
      {oauthNotice ? (
        <div className={`banner ${noticeIsError ? 'banner-error' : 'banner-success'}`} role="status">
          <strong>{oauthNotice}</strong>
          <button type="button" className="secondary-button" onClick={() => setOauthNotice(null)}>
            Dismiss
          </button>
        </div>
      ) : null}

      {needsIntegrations ? (
        <SectionStatus
          loading={integrations.loading}
          error={integrations.error}
          hasData={Boolean(integrations.data)}
          onRetry={integrations.reload}
          loadingText="Loading integrations…"
        />
      ) : null}

      {route.page === 'overview' ? <OverviewPage /> : null}
      {route.page === 'integrations' ? (
        <IntegrationsPage integrations={integrations} onCreate={handleCreate} />
      ) : null}
      {route.page === 'requests' ? <RequestsPage integrations={items} /> : null}
      {route.page === 'telemetry' ? (
        <TelemetryPage
          integrations={items}
          integrationsLoaded={Boolean(integrations.data)}
          requestedIntegrationId={route.params.get('integration')}
        />
      ) : null}
      {route.page === 'webhooks' ? <StripeWebhooksPanel integrations={items} /> : null}
      {route.page === 'failures' ? (
        <FailuresPage integrations={items} onIntegrationsChanged={reloadIntegrations} />
      ) : null}
      {route.page === 'diagnostics' && integrations.data ? (
        <DiagnosticsPage integrations={items} requestedIntegrationId={route.params.get('integration')} />
      ) : null}
      {route.page === 'support' ? <SupportCasesPage integrations={items} /> : null}
      {route.page === 'audit' ? <AuditPage /> : null}
    </AppShell>
  )
}

export default App
