import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { getTelemetryHealth, listTelemetryEvents } from '../api'
import SectionStatus from '../components/SectionStatus'
import { HealthBadge } from '../components/StatusBadges'
import { formatCount, formatErrorRate, formatMs, formatP95, formatTime } from '../format'
import { navigate, pageHref, useResource } from '../hooks'
import { recordForSelection, recordsForSelection } from '../viewSelection'
import type { Integration, TelemetryErrorCategory, TelemetryEvent } from '../types'

const CATEGORIES: TelemetryErrorCategory[] = [
  'http_client_error',
  'rate_limited',
  'http_server_error',
  'timeout',
  'transport_error',
]

function categoryLabel(value: string | null): string {
  if (!value) return '—'
  return value.replaceAll('_', ' ')
}

function TelemetryPage({
  integrations,
  requestedIntegrationId,
}: {
  integrations: Integration[]
  requestedIntegrationId: string | null
}) {
  const instrumented = integrations.filter((item) => item.provider === 'instrumented_http')
  const requestedId =
    instrumented.find((item) => item.id === requestedIntegrationId)?.id ?? instrumented[0]?.id ?? null
  const [integrationId, setIntegrationId] = useState(requestedId)
  if (integrationId !== requestedId) setIntegrationId(requestedId)

  const [service, setService] = useState('')
  const [statusCode, setStatusCode] = useState('')
  const [category, setCategory] = useState<TelemetryErrorCategory | ''>('')
  const [appliedService, setAppliedService] = useState('')
  const [appliedStatusCode, setAppliedStatusCode] = useState('')
  const [appliedCategory, setAppliedCategory] = useState<TelemetryErrorCategory | ''>('')
  const [cursor, setCursor] = useState<string | undefined>(undefined)
  const [previousCursors, setPreviousCursors] = useState<Array<string | undefined>>([])
  const [filterOwner, setFilterOwner] = useState(integrationId)
  if (filterOwner !== integrationId) {
    setFilterOwner(integrationId)
    setService('')
    setStatusCode('')
    setCategory('')
    setAppliedService('')
    setAppliedStatusCode('')
    setAppliedCategory('')
    setCursor(undefined)
    setPreviousCursors([])
  }

  const loadHealth = useCallback(
    () => (integrationId ? getTelemetryHealth(integrationId, 24) : Promise.reject(new Error('No application'))),
    [integrationId],
  )
  const loadEvents = useCallback(async () => {
    if (!integrationId) return Promise.reject(new Error('No application'))
    const parsedStatus = appliedStatusCode.trim() === '' ? undefined : Number(appliedStatusCode)
    const page = await listTelemetryEvents({
      integration_id: integrationId,
      service: appliedService.trim() || undefined,
      status_code: parsedStatus !== undefined && Number.isInteger(parsedStatus) ? parsedStatus : undefined,
      error_category: appliedCategory || undefined,
      limit: 50,
      cursor,
    })
    return { ownerId: integrationId, records: [page] }
  }, [integrationId, appliedService, appliedStatusCode, appliedCategory, cursor])

  const health = useResource(integrationId ? loadHealth : null)
  const events = useResource(integrationId ? loadEvents : null)

  function applyFilters(event: FormEvent) {
    event.preventDefault()
    setAppliedService(service)
    setAppliedStatusCode(statusCode)
    setAppliedCategory(category)
    setCursor(undefined)
    setPreviousCursors([])
    health.reload()
  }

  if (instrumented.length === 0) {
    return (
      <section className="panel">
        <h2>SDK-reported telemetry</h2>
        <p className="empty-state">
          No instrumented applications yet. Register one on{' '}
          <a href={pageHref('integrations')}>Integrations</a>. These observations are not the provider
          request log.
        </p>
      </section>
    )
  }

  const shownHealth = recordForSelection(integrationId, health.data)
  const metrics = shownHealth?.metrics
  const page = recordsForSelection(integrationId, events.data)?.[0]

  return (
    <>
      <section className="banner" role="note">
        <strong>SDK-reported.</strong>
        <p>
          These rows are what the application SDK sent. IntegrationLab did not independently contact
          the upstream service. They are not GitHub or Stripe provider requests.
        </p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Application</h2>
          {shownHealth ? <HealthBadge state={shownHealth.health} /> : null}
        </div>
        <form className="webhook-toolbar" onSubmit={applyFilters}>
          <label>
            Integration
            <select
              value={integrationId ?? ''}
              onChange={(event) => {
                navigate('telemetry', { integration: event.target.value })
                setCursor(undefined)
                setPreviousCursors([])
              }}
            >
              {instrumented.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.environment}
                </option>
              ))}
            </select>
          </label>
          <label>
            Service
            <input value={service} onChange={(event) => setService(event.target.value)} placeholder="orders-api" />
          </label>
          <label>
            Status code
            <input
              inputMode="numeric"
              value={statusCode}
              onChange={(event) => setStatusCode(event.target.value)}
              placeholder="200–599"
            />
          </label>
          <label>
            Failure category
            <select value={category} onChange={(event) => setCategory(event.target.value as TelemetryErrorCategory | '')}>
              <option value="">All</option>
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {categoryLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Apply</button>
        </form>
      </section>

      <SectionStatus
        loading={health.loading}
        error={health.error}
        hasData={Boolean(shownHealth)}
        onRetry={health.reload}
        loadingText="Loading SDK health…"
      />

      {shownHealth && metrics ? (
        <section className="panel">
          <h2>Evidence-backed health</h2>
          <p>{shownHealth.summary}</p>
          <p className="muted small-text">
            Provenance {shownHealth.provenance}. Independently verified: no. Window {shownHealth.window_hours}h.
          </p>
          <div className="summary-grid totals-grid">
            <article className="summary-card">
              <p className="summary-label">Observations</p>
              <p className="summary-value">{formatCount(metrics.request_count)}</p>
            </article>
            <article className="summary-card">
              <p className="summary-label">Successes</p>
              <p className="summary-value">{formatCount(metrics.success_count)}</p>
            </article>
            <article className={`summary-card${metrics.error_count > 0 ? ' total-failed' : ''}`}>
              <p className="summary-label">Errors</p>
              <p className={metrics.error_count > 0 ? 'summary-value' : 'summary-value is-zero'}>
                {formatCount(metrics.error_count)}
              </p>
            </article>
            <article className="summary-card">
              <p className="summary-label">Error rate</p>
              <p className="summary-value summary-value-text">{formatErrorRate(metrics.error_rate)}</p>
            </article>
          </div>
          <dl className="fact-grid">
            <div>
              <dt>Average latency</dt>
              <dd>{formatMs(metrics.average_latency_ms)}</dd>
            </div>
            <div>
              <dt>p95 latency</dt>
              <dd>{formatP95(metrics.p95_latency_ms, metrics.sample_count)}</dd>
            </div>
            <div>
              <dt>Latest</dt>
              <dd>
                {metrics.latest_service ?? '—'} {metrics.latest_route_template ?? ''}{' '}
                {metrics.latest_status_code ?? metrics.latest_error_category ?? '—'}
              </dd>
            </div>
            <div>
              <dt>Samples</dt>
              <dd>{formatCount(metrics.sample_count)}</dd>
            </div>
          </dl>
          {metrics.sample_count < 20 ? (
            <p className="muted small-text">p95 latency stays unavailable until at least 20 observations.</p>
          ) : null}
          {metrics.failure_categories.length > 0 ? (
            <ul className="evidence-list">
              {metrics.failure_categories.map((item) => (
                <li key={item.category}>
                  {categoryLabel(item.category)} · {item.count}
                </li>
              ))}
            </ul>
          ) : null}
          <ul className="evidence-list">
            {shownHealth.evidence.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {shownHealth.recommended_action ? (
            <p className="recommendation">
              <strong>Next step:</strong> {shownHealth.recommended_action}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="panel">
        <div className="panel-header">
          <h2>Observations</h2>
          <button type="button" className="secondary-button" onClick={events.reload}>
            Refresh
          </button>
        </div>
        <SectionStatus
          loading={events.loading}
          error={events.error}
          hasData={Boolean(page)}
          onRetry={events.reload}
          loadingText="Loading SDK observations…"
        />
        {page && page.items.length === 0 ? (
          <p className="empty-state">No SDK-reported observations match these filters.</p>
        ) : null}
        {page && page.items.length > 0 ? <EventTable items={page.items} /> : null}
        <div className="button-row">
          <button
            type="button"
            className="secondary-button"
            disabled={previousCursors.length === 0}
            onClick={() => {
              const prior = previousCursors.slice(0, -1)
              setPreviousCursors(prior)
              setCursor(prior.at(-1))
            }}
          >
            Previous
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!page?.next_cursor}
            onClick={() => {
              if (!page?.next_cursor) return
              setPreviousCursors((items) => [...items, cursor])
              setCursor(page.next_cursor ?? undefined)
            }}
          >
            Next
          </button>
        </div>
      </section>
    </>
  )
}

function EventTable({ items }: { items: TelemetryEvent[] }) {
  return (
    <div className="table-wrap">
      <table className="integrations-table">
        <thead>
          <tr>
            <th>Observed</th>
            <th>Received</th>
            <th>Service</th>
            <th>Method</th>
            <th>Route template</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Category</th>
            <th>Environment</th>
            <th>SDK</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.event_id}>
              <td className="nowrap">{formatTime(item.occurred_at)}</td>
              <td className="nowrap">{formatTime(item.received_at)}</td>
              <td>{item.service}</td>
              <td>{item.method}</td>
              <td>
                <code>{item.route_template}</code>
              </td>
              <td>{item.status_code ?? '—'}</td>
              <td>{formatMs(item.duration_ms)}</td>
              <td>{categoryLabel(item.error_category)}</td>
              <td>{item.environment}</td>
              <td className="muted small-text">
                {item.sdk_name ?? '—'}
                {item.sdk_version ? ` ${item.sdk_version}` : ''}
                <div>SDK-reported</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default TelemetryPage
