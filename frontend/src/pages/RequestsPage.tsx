import { useCallback, useState } from 'react'
import { getRequestMetrics, listProviderRequests } from '../api'
import ProviderRequestsTable from '../components/ProviderRequestsTable'
import SectionStatus from '../components/SectionStatus'
import { formatCount, formatMs } from '../format'
import { useResource } from '../hooks'
import type { Integration } from '../types'

type SourceFilter = 'real' | 'simulated' | 'all'

const WINDOW_HOURS = 24

function simulatedParam(source: SourceFilter): boolean | undefined {
  if (source === 'all') return undefined
  return source === 'simulated'
}

function RequestsPage({ integrations }: { integrations: Integration[] }) {
  const [provider, setProvider] = useState('')
  const [source, setSource] = useState<SourceFilter>('real')
  const [integrationId, setIntegrationId] = useState('')

  const loadMetrics = useCallback(
    () =>
      getRequestMetrics({
        provider: provider || undefined,
        integration_id: integrationId || undefined,
        is_simulated: simulatedParam(source),
        window_hours: WINDOW_HOURS,
      }),
    [provider, integrationId, source],
  )
  const loadLogs = useCallback(
    () =>
      listProviderRequests({
        provider: provider || undefined,
        integration_id: integrationId || undefined,
        is_simulated: simulatedParam(source),
        limit: 50,
      }),
    [provider, integrationId, source],
  )
  const metrics = useResource(loadMetrics)
  const logs = useResource(loadLogs)
  const m = metrics.data?.metrics

  const cards: [string, string][] = [
    [`Requests (${WINDOW_HOURS}h)`, formatCount(m?.request_count)],
    ['Errors', m ? `${m.failure_count}${m.request_count ? ` / ${m.request_count}` : ''}` : '—'],
    ['Avg latency', formatMs(m?.average_latency_ms)],
    ['p95 latency', formatMs(m?.p95_latency_ms)],
  ]

  return (
    <>
      <section className="panel">
        <div className="webhook-toolbar">
          <label>
            Provider
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="">All</option>
              <option value="github">GitHub</option>
              <option value="stripe">Stripe</option>
            </select>
          </label>
          <label>
            Source
            <select value={source} onChange={(e) => setSource(e.target.value as SourceFilter)}>
              <option value="real">Real only</option>
              <option value="simulated">Simulated only</option>
              <option value="all">Real + simulated</option>
            </select>
          </label>
          <label>
            Integration
            <select value={integrationId} onChange={(e) => setIntegrationId(e.target.value)}>
              <option value="">All</option>
              {integrations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.provider})
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              metrics.reload()
              logs.reload()
            }}
          >
            Refresh
          </button>
        </div>
      </section>

      <section>
        <SectionStatus loading={metrics.loading} error={metrics.error} hasData={Boolean(m)} onRetry={metrics.reload} />
        <div className="summary-grid totals-grid">
          {cards.map(([label, value]) => (
            <article key={label} className="summary-card">
              <p className="summary-label">{label}</p>
              <p className="summary-value">{value}</p>
            </article>
          ))}
        </div>
        <p className="muted small-text">
          Metrics cover the last {WINDOW_HOURS}h; p95 is nearest-rank over the matching requests (sample
          size shown in Errors).
        </p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Recent provider requests</h2>
          <span className="muted small-text">Latest 50 matching</span>
        </div>
        <p className="muted">
          Outbound calls IntegrationLab makes to providers. Inbound Stripe webhooks appear on the Webhooks
          page instead.
        </p>
        <SectionStatus
          loading={logs.loading}
          error={logs.error}
          hasData={Boolean(logs.data)}
          onRetry={logs.reload}
          loadingText="Loading requests…"
        />
        {logs.data ? <ProviderRequestsTable logs={logs.data} /> : null}
      </section>
    </>
  )
}

export default RequestsPage
