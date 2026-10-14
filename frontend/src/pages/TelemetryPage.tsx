import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { getTelemetryHealth, listIngestionCredentials, listTelemetryEvents } from '../api'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import LedgerList, { HealthWord, LedgerFilters } from '../components/ledger/LedgerList'
import ObservationSequence from '../components/ledger/ObservationSequence'
import SupportCaseDrawer from '../components/ledger/SupportCaseDrawer'
import SectionStatus from '../components/SectionStatus'
import { formatErrorRate, formatMs, formatP95, formatTime } from '../format'
import { navigate, pageHref, useResource } from '../hooks'
import { draftFromTelemetry, type CaseDraft } from '../ledger/case'
import { telemetryFinding } from '../ledger/copy'
import { marksFromTelemetry } from '../ledger/sequence'
import { telemetryStations } from '../ledger/trail'
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

function matchesEvent(event: TelemetryEvent, service: string, statusCode: string, category: string): boolean {
  if (service && !event.service.toLowerCase().includes(service.trim().toLowerCase())) return false
  if (statusCode.trim() && String(event.status_code ?? '') !== statusCode.trim()) return false
  if (category && event.error_category !== category) return false
  return true
}

function TelemetryPage({
  integrations,
  integrationsLoaded,
  requestedIntegrationId,
}: {
  integrations: Integration[]
  integrationsLoaded: boolean
  requestedIntegrationId: string | null
}) {
  const instrumented = integrations.filter((item) => item.provider === 'instrumented_http')
  const requestedId =
    instrumented.find((item) => item.id === requestedIntegrationId)?.id ?? instrumented[0]?.id ?? null
  const [integrationId, setIntegrationId] = useState(requestedId)
  if (integrationId !== requestedId) setIntegrationId(requestedId)

  const [windowHours, setWindowHours] = useState(24)
  const [service, setService] = useState('')
  const [statusCode, setStatusCode] = useState('')
  const [category, setCategory] = useState<TelemetryErrorCategory | ''>('')
  const [appliedService, setAppliedService] = useState('')
  const [appliedStatusCode, setAppliedStatusCode] = useState('')
  const [appliedCategory, setAppliedCategory] = useState<TelemetryErrorCategory | ''>('')
  const [cursor, setCursor] = useState<string | undefined>(undefined)
  const [previousCursors, setPreviousCursors] = useState<Array<string | undefined>>([])
  const [pickedEventId, setPickedEventId] = useState<string | null>(null)
  const [draft, setDraft] = useState<CaseDraft | null>(null)
  const closeDrawer = useCallback(() => setDraft(null), [])
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
    setPickedEventId(null)
  }

  const loadHealth = useCallback(
    () => (integrationId ? getTelemetryHealth(integrationId, windowHours) : Promise.reject(new Error('No application'))),
    [integrationId, windowHours],
  )
  const loadEvents = useCallback(async () => {
    if (!integrationId) return Promise.reject(new Error('No application'))
    const parsedStatus = appliedStatusCode.trim() === '' ? undefined : Number(appliedStatusCode)
    const occurredAfter = new Date(Date.now() - windowHours * 3600_000).toISOString()
    const page = await listTelemetryEvents({
      integration_id: integrationId,
      service: appliedService.trim() || undefined,
      status_code: parsedStatus !== undefined && Number.isInteger(parsedStatus) ? parsedStatus : undefined,
      error_category: appliedCategory || undefined,
      occurred_after: occurredAfter,
      limit: 50,
      cursor,
    })
    return {
      ownerId: `${integrationId}:${windowHours}:${appliedService}:${appliedStatusCode}:${appliedCategory}:${cursor ?? ''}`,
      records: [page],
    }
  }, [integrationId, appliedService, appliedStatusCode, appliedCategory, cursor, windowHours])
  const loadSequence = useCallback(async () => {
    if (!integrationId) return Promise.reject(new Error('No application'))
    const occurredAfter = new Date(Date.now() - windowHours * 3600_000).toISOString()
    const page = await listTelemetryEvents({
      integration_id: integrationId,
      occurred_after: occurredAfter,
      limit: 50,
    })
    return { ownerId: `${integrationId}:${windowHours}`, records: page.items }
  }, [integrationId, windowHours])
  const loadCredentials = useCallback(async () => {
    if (!integrationId) return Promise.reject(new Error('No application'))
    const records = await listIngestionCredentials(integrationId)
    return { ownerId: integrationId, records }
  }, [integrationId])

  const health = useResource(integrationId ? loadHealth : null)
  const events = useResource(integrationId ? loadEvents : null)
  const sequence = useResource(integrationId ? loadSequence : null)
  const credentials = useResource(integrationId ? loadCredentials : null)

  function applyFilters(event: FormEvent) {
    event.preventDefault()
    setAppliedService(service)
    setAppliedStatusCode(statusCode)
    setAppliedCategory(category)
    setCursor(undefined)
    setPreviousCursors([])
  }

  if (!integrationsLoaded) return null

  if (instrumented.length === 0) {
    return (
      <section>
        <h1 className="lg-finding">No instrumented applications yet.</h1>
        <p className="lg-note">
          Register one on <a href={pageHref('integrations')}>Integrations</a>. These observations are not the
          provider request log.
        </p>
      </section>
    )
  }

  const loadedHealth = recordForSelection(integrationId, health.data)
  const shownHealth = loadedHealth?.window_hours === windowHours ? loadedHealth : undefined
  const eventScope = integrationId
    ? `${integrationId}:${windowHours}:${appliedService}:${appliedStatusCode}:${appliedCategory}:${cursor ?? ''}`
    : null
  const page = recordsForSelection(eventScope, events.data)?.[0]
  const sequenceEvents = recordsForSelection(integrationId ? `${integrationId}:${windowHours}` : null, sequence.data)
  const credentialRows = recordsForSelection(integrationId, credentials.data)
  const activePrefix = credentialRows?.find((item) => item.revoked_at === null)?.key_prefix ?? null
  const latest = [...(sequenceEvents ?? [])].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at)).at(-1) ?? null
  const selectedEvent =
    sequenceEvents?.find((item) => item.event_id === pickedEventId) ??
    page?.items.find((item) => item.event_id === pickedEventId) ??
    latest
  const marks = sequenceEvents
    ? marksFromTelemetry(sequenceEvents, {
        selectedId: selectedEvent?.event_id,
        dimmed: (item) => !matchesEvent(item, appliedService, appliedStatusCode, appliedCategory),
      })
    : []
  const finding = shownHealth ? telemetryFinding(shownHealth) : 'SDK telemetry'
  const stations = telemetryStations(selectedEvent ?? null, shownHealth, activePrefix)

  function openCase(eventId?: string) {
    const event =
      sequenceEvents?.find((item) => item.event_id === eventId) ??
      page?.items.find((item) => item.event_id === eventId) ??
      selectedEvent
    if (!event) return
    setPickedEventId(event.event_id)
    setDraft(draftFromTelemetry(event, shownHealth))
  }

  return (
    <div className={health.loading || events.loading ? 'lg-busy' : undefined} aria-busy={health.loading || events.loading || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker" role="status">
            Telemetry · last {windowHours}h
            {health.loading || events.loading ? <span className="lg-refresh">Refreshing…</span> : null}
          </p>
          <h1 className="lg-finding">{finding}</h1>
          {shownHealth ? (
            <p className="lg-status">
              <HealthWord state={shownHealth.health} />
              <span>{shownHealth.summary}</span>
            </p>
          ) : null}
          <p className="lg-note">SDK-reported. IntegrationLab did not contact the upstream service.</p>
          <form className="lg-toolbar" onSubmit={applyFilters}>
            <label className="lg-field">
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
            <LedgerFilters
              label="Window"
              value={String(windowHours)}
              onChange={(id) => {
                setWindowHours(Number(id))
                setCursor(undefined)
                setPreviousCursors([])
              }}
              options={[
                { id: '24', label: '24h' },
                { id: '168', label: '7 days' },
              ]}
            />
            <label className="lg-field">
              Service
              <input value={service} onChange={(event) => setService(event.target.value)} placeholder="orders-api" />
            </label>
            <label className="lg-field">
              Status code
              <input
                inputMode="numeric"
                value={statusCode}
                onChange={(event) => setStatusCode(event.target.value)}
                placeholder="200–599"
              />
            </label>
            <label className="lg-field">
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
          <SectionStatus
            loading={health.loading}
            error={health.error}
            hasData={Boolean(shownHealth)}
            onRetry={health.reload}
            loadingText="Loading SDK health…"
          />
          {shownHealth ? (
            <RuleFacts
              rows={[
                ['Observations', String(shownHealth.metrics.request_count)],
                ['Errors', String(shownHealth.metrics.error_count)],
                ['Error rate', formatErrorRate(shownHealth.metrics.error_rate)],
                ['p95', formatP95(shownHealth.metrics.p95_latency_ms, shownHealth.metrics.sample_count)],
              ]}
            />
          ) : null}
          {shownHealth && shownHealth.metrics.sample_count < 20 ? (
            <p className="lg-note">p95 latency stays unavailable until at least 20 observations.</p>
          ) : null}
          <SectionStatus
            loading={sequence.loading}
            error={sequence.error}
            hasData={Boolean(sequenceEvents)}
            onRetry={sequence.reload}
            loadingText="Loading observations…"
          />
          {sequenceEvents ? (
            <ObservationSequence marks={marks} onSelect={setPickedEventId} />
          ) : null}
          <p className="lg-section-label">Observations</p>
          <SectionStatus
            loading={events.loading}
            error={events.error}
            hasData={Boolean(page)}
            onRetry={events.reload}
            loadingText="Loading SDK observations…"
          />
          {page && page.items.length === 0 ? <p className="lg-empty">No SDK-reported observations match these filters.</p> : null}
          {page && page.items.length > 0 ? (
            <LedgerList
              label="SDK observations"
              columns={['Observed', 'Route', 'Status', 'Duration', 'Category']}
              rows={page.items.map((item) => ({
                id: item.event_id,
                title: `${item.method} ${item.route_template}`,
                meta: item.status_code ?? categoryLabel(item.error_category),
                detail: formatTime(item.occurred_at),
                cells: [
                  formatTime(item.occurred_at),
                  <span key="route" className="lg-mono">
                    {item.method} {item.route_template}
                  </span>,
                  item.status_code ?? '—',
                  formatMs(item.duration_ms),
                  categoryLabel(item.error_category),
                ],
              }))}
              selectedId={selectedEvent?.event_id ?? null}
              onSelect={setPickedEventId}
              onOpen={(id) => openCase(id)}
              emptyText="No SDK-reported observations match these filters."
            />
          ) : null}
          <div className="lg-pager">
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
          {selectedEvent ? (
            <div className="lg-mobile-action">
              <button type="button" className="lg-case-button" onClick={() => openCase(selectedEvent.event_id)}>
                Open support case
              </button>
            </div>
          ) : null}
        </div>
        <EvidenceTrail
          title="Evidence"
          stations={stations}
          action={
            selectedEvent ? (
              <button type="button" className="lg-case-button" onClick={() => openCase(selectedEvent.event_id)}>
                Open support case
              </button>
            ) : null
          }
        />
      </div>
      {draft ? <SupportCaseDrawer key={`${draft.integrationId}:${draft.title}`} draft={draft} onClose={closeDrawer} /> : null}
    </div>
  )
}

function RuleFacts({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="lg-rules">
      {rows.map(([label, text]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{text}</dd>
        </div>
      ))}
    </dl>
  )
}

export default TelemetryPage
