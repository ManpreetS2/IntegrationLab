import { useCallback, useState } from 'react'
import { getRequestMetrics, listProviderRequests } from '../api'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import LedgerList, { LedgerFilters } from '../components/ledger/LedgerList'
import SectionStatus from '../components/SectionStatus'
import { formatCount, formatMs, formatProvider, formatTime } from '../format'
import { pageHref, useResource } from '../hooks'
import { shorten } from '../ledger/copy'
import type { Integration, ProviderRequestLog } from '../types'

type SourceFilter = 'real' | 'simulated' | 'all'

const WINDOW_HOURS = 24

function simulatedParam(source: SourceFilter): boolean | undefined {
  if (source === 'all') return undefined
  return source === 'simulated'
}

function requestFinding(count: number | undefined, failures: number | undefined, source: SourceFilter): string {
  if (count === undefined) return 'Requests'
  const kind = source === 'simulated' ? 'simulated requests' : source === 'all' ? 'requests' : 'provider requests'
  if (count === 0) return `No ${kind} in this window.`
  if ((failures ?? 0) > 0) return `${failures} of ${count} ${kind} failed.`
  return count === 1 ? `One ${kind.replace(/s$/, '')} succeeded.` : `${count} ${kind} succeeded.`
}

function RequestsPage({ integrations }: { integrations: Integration[] }) {
  const [provider, setProvider] = useState('')
  const [source, setSource] = useState<SourceFilter>('real')
  const [integrationId, setIntegrationId] = useState('')
  const [pickedId, setPickedId] = useState<string | null>(null)

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
  const rows = logs.data ?? []
  const selected = rows.find((item) => item.id === pickedId) ?? rows[0] ?? null
  const providers = integrations.filter((item) => item.provider !== 'instrumented_http')

  return (
    <div className={logs.loading ? 'lg-busy' : undefined} aria-busy={logs.loading || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker">
            Requests · last {WINDOW_HOURS}h · {source === 'real' ? 'real traffic' : source === 'simulated' ? 'simulated' : 'real and simulated'}
            {metrics.loading ? <span className="lg-refresh">Refreshing…</span> : null}
          </p>
          <h1 className="lg-finding">{requestFinding(m?.request_count, m?.failure_count, source)}</h1>
          <p className="lg-note">
            Independently recorded calls IntegrationLab makes to providers. SDK-reported observations stay on{' '}
            <a href={pageHref('telemetry')}>Telemetry</a>.
          </p>
          <div className="lg-toolbar">
            <LedgerFilters
              label="Source"
              value={source}
              onChange={(id) => setSource(id as SourceFilter)}
              options={[
                { id: 'real', label: 'Real' },
                { id: 'simulated', label: 'Simulated' },
                { id: 'all', label: 'Both' },
              ]}
            />
            <LedgerFilters
              label="Provider"
              value={provider || 'all'}
              onChange={(id) => setProvider(id === 'all' ? '' : id)}
              options={[
                { id: 'all', label: 'All' },
                { id: 'github', label: 'GitHub' },
                { id: 'stripe', label: 'Stripe' },
              ]}
            />
          </div>
          <label className="lg-field">
            Integration
            <select value={integrationId} onChange={(event) => setIntegrationId(event.target.value)}>
              <option value="">All</option>
              {providers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {formatProvider(item.provider)}
                </option>
              ))}
            </select>
          </label>
          <SectionStatus loading={metrics.loading} error={metrics.error} hasData={Boolean(m)} onRetry={metrics.reload} />
          {m ? (
            <dl className="lg-metrics">
              <div>
                <dt>Requests</dt>
                <dd>{formatCount(m.request_count)}</dd>
              </div>
              <div>
                <dt>Errors</dt>
                <dd className={m.failure_count > 0 ? 'lg-health-bad' : undefined}>
                  {m.failure_count}
                  {m.request_count ? ` / ${m.request_count}` : ''}
                </dd>
              </div>
              <div>
                <dt>Average</dt>
                <dd>{formatMs(m.average_latency_ms)}</dd>
              </div>
              <div>
                <dt>p95</dt>
                <dd>{formatMs(m.p95_latency_ms)}</dd>
              </div>
            </dl>
          ) : null}
          <p className="lg-metric-note">p95 is nearest-rank over the matching requests in this window.</p>
          <SectionStatus
            loading={logs.loading}
            error={logs.error}
            hasData={Boolean(logs.data)}
            onRetry={logs.reload}
            loadingText="Loading requests…"
          />
          {logs.data ? (
            <LedgerList
              label="Provider requests"
              columns={['When', 'Call', 'Status', 'Latency']}
              rows={rows.map((item) => ({
                id: item.id,
                title: `${item.method} ${item.endpoint}`,
                meta: item.is_simulated ? 'Simulated' : formatProvider(item.provider),
                detail: `${item.status_code ?? item.error_message ?? '—'} · ${formatMs(item.latency_ms)}`,
                cells: [
                  formatTime(item.timestamp),
                  <span key="call" className="lg-mono">
                    {item.method} {item.endpoint}
                  </span>,
                  item.status_code ?? item.error_message ?? '—',
                  formatMs(item.latency_ms),
                ],
              }))}
              selectedId={selected?.id ?? null}
              onSelect={setPickedId}
              emptyText="No provider requests match these filters."
            />
          ) : null}
        </div>
        <EvidenceTrail title={selected ? 'Request' : 'No request selected'} stations={requestStations(selected)} />
      </div>
    </div>
  )
}

function requestStations(item: ProviderRequestLog | null) {
  if (!item) return [{ label: 'Log', text: 'Select a request. Simulated rows stay labeled and are not live provider health.' }]
  return [
    { label: 'Call', text: `${item.method} ${item.endpoint}` },
    { label: 'Result', text: `${item.status_code ?? 'No status'} · ${formatMs(item.latency_ms)}` },
    { label: 'Source', text: item.is_simulated ? `Simulated${item.scenario ? ` · ${item.scenario}` : ''}` : 'Real provider traffic' },
    { label: 'Error', text: shorten(item.error_message ?? 'None recorded', 140) },
    {
      label: 'Rate limit',
      text: item.rate_limit_remaining === null ? 'Not reported' : `${item.rate_limit_remaining} remaining`,
    },
  ]
}

export default RequestsPage
