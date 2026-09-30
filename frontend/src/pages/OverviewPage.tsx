import { useCallback, useEffect, useState } from 'react'
import { ApiError, getReliabilityOverview, listReliabilityFailures } from '../api'
import FailuresTable from '../components/FailuresTable'
import IntegrationHealthCard from '../components/IntegrationHealthCard'
import SectionStatus from '../components/SectionStatus'
import { formatCount, formatTime } from '../format'
import { useResource } from '../hooks'
import type { HealthState, OperationalMetrics } from '../types'

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
              <dd>{formatCount(value)}</dd>
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
              <dd>{formatCount(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
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
          <div className="summary-grid totals-grid">
            {TOTAL_CARDS.map((card) => (
              <article key={card.state} className={`summary-card total-${card.state}`}>
                <p className="summary-label">{card.label}</p>
                <p className="summary-value">{data.totals[card.state]}</p>
              </article>
            ))}
            <article className="summary-card">
              <p className="summary-label">Database</p>
              <p className="summary-value summary-value-text">
                {data.system.database === 'healthy' ? 'Reachable' : 'Unavailable'}
              </p>
            </article>
          </div>
          {data.totals.not_configured > 0 ? (
            <p className="muted small-text">
              {data.totals.not_configured} integration(s) not configured yet (excluded from the counts above).
            </p>
          ) : null}

          <section className="panel">
            <div className="panel-header">
              <h2>Integration health</h2>
              <span className="muted small-text">Derived from stored evidence only — no provider calls.</span>
            </div>
            {data.integrations.length === 0 ? (
              <p className="empty-state">No integrations yet. Create one on the Integrations page.</p>
            ) : (
              <div className="health-grid">
                {data.integrations.map((item) => (
                  <IntegrationHealthCard key={item.integration_id} item={item} windowHours={data.window_hours} />
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
