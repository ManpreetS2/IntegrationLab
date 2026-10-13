import { useCallback, useEffect, useState } from 'react'
import { ApiError, getReliabilityOverview, listReliabilityFailures } from '../api'
import FailuresTable from '../components/FailuresTable'
import { HealthBadge } from '../components/StatusBadges'
import IntegrationHealthCard from '../components/IntegrationHealthCard'
import SectionStatus from '../components/SectionStatus'
import { formatCount, formatProvider, formatTime } from '../format'
import { pageHref, useResource } from '../hooks'
import type { HealthState, IntegrationHealth, OperationalMetrics } from '../types'

const AUTO_REFRESH_MS = 60_000

const TOTAL_CARDS: { state: HealthState; label: string }[] = [
  { state: 'healthy', label: 'Healthy' },
  { state: 'degraded', label: 'Degraded' },
  { state: 'failed', label: 'Failed' },
  { state: 'unknown', label: 'Unknown' },
]

function loadOverview() {
  return getReliabilityOverview(24)
}

const ALERT_LABELS = new Set(['Real provider errors', 'Failed', 'SDK-reported errors'])

function metricClass(label: string, value: number): string | undefined {
  if (ALERT_LABELS.has(label) && value > 0) return 'is-alert'
  return undefined
}

function headline(failed: number, degraded: number, count: number): string {
  if (failed > 0 && degraded > 0) return `${failed} failed and ${degraded} degraded.`
  if (failed === 1) return 'One integration has failed.'
  if (failed > 1) return `${failed} integrations have failed.`
  if (degraded === 1) return 'One integration needs attention.'
  if (degraded > 1) return `${degraded} integrations need attention.`
  if (count === 0) return 'No integrations yet.'
  return 'Stored evidence shows no failing integrations.'
}

function OperationalGrid({ metrics, windowHours }: { metrics: OperationalMetrics; windowHours: number }) {
  const windowed: [string, number][] = [
    ['Real provider requests', metrics.real_provider_requests],
    ['Real provider errors', metrics.real_provider_errors],
    ['Simulated requests', metrics.simulated_requests],
    ['Failure Lab runs', metrics.failure_lab_runs],
    ['Webhook events received', metrics.webhook_events_received],
    ['Duplicate deliveries absorbed', metrics.duplicate_webhook_deliveries],
    ['Diagnostic runs', metrics.diagnostic_runs],
  ]
  const sdk: [string, number][] = [
    ['SDK-reported observations', metrics.sdk_reported_observations ?? 0],
    ['SDK-reported errors', metrics.sdk_reported_errors ?? 0],
  ]
  const queue: [string, number][] = [
    ['Processed', metrics.webhook_processed],
    ['Pending', metrics.webhook_pending],
    ['Retry scheduled', metrics.webhook_retry_scheduled],
    ['Failed', metrics.webhook_failed],
  ]
  return (
    <div className="metric-groups">
      <div>
        <h3 className="group-title">Last {windowHours}h</h3>
        <dl className="metric-list">
          {windowed.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className={metricClass(label, value)}>{formatCount(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div>
        <h3 className="group-title">SDK-reported, not verified</h3>
        <p className="muted small-text">These counts are not included in real provider requests.</p>
        <dl className="metric-list">
          {sdk.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className={metricClass(label, value)}>{formatCount(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div>
        <h3 className="group-title">Current webhook queue</h3>
        <dl className="metric-list">
          {queue.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className={metricClass(label, value)}>{formatCount(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

const HEALTH_RANK: Record<HealthState, number> = {
  failed: 0,
  degraded: 1,
  unknown: 2,
  healthy: 3,
  not_configured: 4,
}

function ordered(items: IntegrationHealth[]): IntegrationHealth[] {
  return [...items].sort((a, b) => HEALTH_RANK[a.health] - HEALTH_RANK[b.health])
}

function Attention({ items }: { items: IntegrationHealth[] }) {
  const attention = items.filter((item) => item.health === 'failed' || item.health === 'degraded')
  if (attention.length === 0) return null
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Needs attention</h2>
      </div>
      <div className="health-list">
        {attention.map((item) => (
          <article key={item.integration_id} className="health-row">
            <div className="health-row-main">
              <span className="provider-mark" aria-hidden="true">
                {item.provider.slice(0, 1).toUpperCase()}
              </span>
              <span className="health-row-copy">
                <strong>{item.name}</strong>
                <span>
                  {formatProvider(item.provider)} · {item.summary}
                </span>
              </span>
              <HealthBadge state={item.health} />
              <a
                className="button-link"
                href={
                  item.provider === 'instrumented_http'
                    ? pageHref('telemetry', { integration: item.integration_id })
                    : pageHref('diagnostics', { integration: item.integration_id })
                }
              >
                Inspect
              </a>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

function OverviewPage() {
  const [includeSimulated, setIncludeSimulated] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)

  const overview = useResource(loadOverview)
  const loadFailures = useCallback(
    () => listReliabilityFailures({ include_simulated: includeSimulated, limit: 10, window_hours: 24 }),
    [includeSimulated],
  )
  const failures = useResource(loadFailures)
  const reloadOverview = overview.reload
  const reloadFailures = failures.reload

  const refreshAll = useCallback(() => {
    reloadOverview()
    reloadFailures()
  }, [reloadOverview, reloadFailures])

  useEffect(() => {
    if (!autoRefresh) return
    const timer = window.setInterval(refreshAll, AUTO_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [autoRefresh, refreshAll])

  const data = overview.data
  const databaseDown = overview.error instanceof ApiError && overview.error.status === 503
  const refreshing = overview.loading || failures.loading

  return (
    <>
      <section className="toolbar-row">
        <p className="muted small-text">
          {data ? `Generated ${formatTime(data.generated_at)} · window ${data.window_hours}h` : 'Not loaded yet'}
          {refreshing && data ? ' · Refreshing…' : ''}
        </p>
        <div className="toolbar-actions">
          <label className="inline-check">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto-refresh (60s)
          </label>
          <button type="button" className="secondary-button" onClick={refreshAll} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      {databaseDown ? (
        <div className="banner banner-error" role="alert">
          <strong>Database unavailable</strong>
          <p>
            Reliability data cannot be read right now. Integration health is not being evaluated, so
            no integration is marked failed because of this.
          </p>
        </div>
      ) : (
        <SectionStatus
          loading={overview.loading}
          error={overview.error}
          hasData={Boolean(data)}
          onRetry={overview.reload}
          loadingText="Loading reliability overview…"
        />
      )}

      {data && !databaseDown ? (
        <>
          <section className="overview-intro">
            <h2>{headline(data.totals.failed, data.totals.degraded, data.integrations.length)}</h2>
            <p>
              Live health uses stored real evidence only. Simulated failures never alter provider health.
              {data.totals.not_configured > 0
                ? ` ${data.totals.not_configured} integration${data.totals.not_configured === 1 ? '' : 's'} not configured yet, excluded from the counts.`
                : ''}
            </p>
          </section>

          <div className="summary-grid totals-grid">
            {TOTAL_CARDS.map((card) => {
              const value = data.totals[card.state]
              return (
                <article key={card.state} className={`summary-card total-${card.state}`}>
                  <p className="summary-label">{card.label}</p>
                  <p className={value === 0 ? 'summary-value is-zero' : 'summary-value'}>{value}</p>
                </article>
              )
            })}
          </div>

          <Attention items={data.integrations} />

          <section className="panel">
            <div className="panel-header">
              <h2>Integrations</h2>
            </div>
            {data.integrations.length === 0 ? (
              <p className="empty-state">No integrations yet. Create one on the Integrations page.</p>
            ) : (
              <div className="health-list">
                {ordered(data.integrations).map((item) => (
                  <IntegrationHealthCard
                    key={item.integration_id}
                    item={item}
                    windowHours={data.window_hours}
                    defaultOpen={item.health === 'failed' || item.health === 'degraded'}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}

      <section className="panel">
        <div className="panel-header">
          <h2>Recent failures</h2>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={includeSimulated}
              onChange={(e) => setIncludeSimulated(e.target.checked)}
            />
            Include simulations
          </label>
        </div>
        <SectionStatus
          loading={failures.loading}
          error={failures.error}
          hasData={Boolean(failures.data)}
          onRetry={failures.reload}
          loadingText="Loading failures…"
        />
        {failures.data ? (
          <FailuresTable
            items={failures.data}
            emptyText={
              includeSimulated
                ? 'No failures in the last 24h.'
                : 'No real failures in the last 24h. Failure Lab simulations are hidden.'
            }
          />
        ) : null}
      </section>

      {data && !databaseDown ? (
        <section className="panel">
          <h2>Operational metrics</h2>
          <p className="muted small-text">
            Counts from stored logs and events. No uptime or SLA figures are computed.
          </p>
          <OperationalGrid metrics={data.operational} windowHours={data.window_hours} />
        </section>
      ) : null}
    </>
  )
}

export default OverviewPage
