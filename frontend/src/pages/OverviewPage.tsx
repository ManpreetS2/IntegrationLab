import { useCallback, useEffect, useState } from 'react'
import { getIntegrationReliability, getReliabilityOverview } from '../api'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import LedgerList, { HealthWord, LedgerFilters, RuleList } from '../components/ledger/LedgerList'
import ObservationSequence from '../components/ledger/ObservationSequence'
import SupportCaseDrawer from '../components/ledger/SupportCaseDrawer'
import SectionStatus from '../components/SectionStatus'
import { formatCount, formatProvider, formatTime } from '../format'
import { pageHref, useResource } from '../hooks'
import { draftFromIntegration, type CaseDraft } from '../ledger/case'
import {
  attentionHeadline,
  emptyWindowSequence,
  latestActivity,
  matchesOverviewFilter,
  shorten,
  whyRows,
  windowTally,
  type OverviewFilter,
} from '../ledger/copy'
import { marksFromRequests, marksFromTelemetry, marksFromWebhooks, type SequenceMark } from '../ledger/sequence'
import { integrationStations } from '../ledger/trail'
import { recordForSelection } from '../viewSelection'
import type { HealthState, IntegrationReliabilityDetail, OperationalMetrics } from '../types'

const AUTO_REFRESH_MS = 60_000

const ALERT_LABELS = new Set(['Real provider errors', 'Failed', 'SDK-reported errors'])

function OverviewPage() {
  const [windowHours, setWindowHours] = useState(24)
  const [filter, setFilter] = useState<OverviewFilter>('all')
  const [pickedId, setPickedId] = useState<string | null>(null)
  const [markId, setMarkId] = useState<string | null>(null)
  const [draft, setDraft] = useState<CaseDraft | null>(null)
  const closeDrawer = useCallback(() => setDraft(null), [])

  const loadOverview = useCallback(() => getReliabilityOverview(windowHours), [windowHours])
  const overview = useResource(loadOverview)
  const reload = overview.reload

  useEffect(() => {
    const timer = window.setInterval(reload, AUTO_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [reload])

  const data = overview.data
  const items = data?.integrations ?? []
  const visible = items.filter((item) => matchesOverviewFilter(item, filter))
  const selected =
    visible.find((item) => item.integration_id === pickedId) ??
    (pickedId === null
      ? (visible.find((item) => item.health === 'degraded' || item.health === 'failed') ?? visible[0] ?? null)
      : (visible[0] ?? null))

  const selectedId = selected?.integration_id ?? null
  const detail = useIntegrationDetail(selectedId, windowHours)
  const loadedDetail = recordForSelection(selected?.integration_id, detail.data)
  const shown = loadedDetail?.window_hours === windowHours ? loadedDetail : undefined
  const marks = shown ? marksForDetail(shown, markId) : []
  const selectedMark = marks.find((mark) => mark.id === markId) ?? null

  const failed = data?.totals.failed ?? 0
  const degraded = data?.totals.degraded ?? 0
  const finding = data ? attentionHeadline(failed, degraded, items.length) : 'Overview'
  const stations = [
    ...(selectedMark
      ? [{ label: 'Selected', text: shorten(`${selectedMark.title} · ${selectedMark.detail}`, 140) }]
      : []),
    ...(selected ? integrationStations(selected, windowHours) : []),
  ].slice(0, 5)

  function openCase(id: string) {
    const item = visible.find((entry) => entry.integration_id === id) ?? selected
    if (!item) return
    setPickedId(item.integration_id)
    setDraft(draftFromIntegration(item))
  }

  return (
    <div className={overview.loading ? 'lg-busy' : undefined} aria-busy={overview.loading || undefined}>
      <SectionStatus
        loading={overview.loading}
        error={overview.error}
        hasData={Boolean(data)}
        onRetry={overview.reload}
        loadingText="Loading overview…"
      />
      {data ? (
        <div className="lg-page">
          <div className="lg-main">
            <p className="lg-kicker" role="status">
              Overview · last {windowHours}h
              {overview.loading ? <span className="lg-refresh">Refreshing…</span> : null}
            </p>
            <h1 className="lg-finding">{finding}</h1>
            <p className="lg-status">
              <CountLamp count={data.totals.failed} state="failed" label="failed" />
              <CountLamp count={data.totals.degraded} state="degraded" label="degraded" />
              <span className="lg-count is-zero">
                {data.totals.healthy} healthy · {data.totals.unknown} unknown · {data.totals.not_configured} not configured
              </span>
            </p>
            <div className="lg-toolbar">
              <LedgerFilters
                label="Integrations"
                value={filter}
                onChange={(id) => setFilter(id as OverviewFilter)}
                options={[
                  { id: 'all', label: `All ${items.length}` },
                  {
                    id: 'attention',
                    label: `Needs attention ${items.filter((item) => item.health === 'degraded' || item.health === 'failed').length}`,
                  },
                  { id: 'sdk', label: 'SDK' },
                  { id: 'webhook', label: 'Webhooks' },
                  { id: 'quiet', label: 'Not configured' },
                ]}
              />
              <LedgerFilters
                label="Window"
                value={String(windowHours)}
                onChange={(id) => setWindowHours(Number(id))}
                options={[
                  { id: '24', label: '24h' },
                  { id: '168', label: '7 days' },
                ]}
              />
            </div>
            <p className="lg-note">
              Showing {visible.length} of {items.length}.
            </p>
            <LedgerList
              label="Integrations"
              columns={['Integration', 'Health', 'Window', 'Latest']}
              rows={visible.map((item) => ({
                id: item.integration_id,
                title: item.name,
                meta: <HealthWord state={item.health} />,
                detail: `${windowTally(item)} · ${latestActivity(item)}`,
                cells: [
                  <span key="name">
                    <strong>{item.name}</strong>
                    <span className="lg-muted"> · {formatProvider(item.provider)}</span>
                  </span>,
                  <HealthWord key="health" state={item.health} />,
                  windowTally(item),
                  <span key="latest" className="lg-mono">
                    {latestActivity(item)}
                  </span>,
                ],
              }))}
              selectedId={selected?.integration_id ?? null}
              onSelect={(id) => {
                setPickedId(id)
                setMarkId(null)
              }}
              onOpen={openCase}
              emptyText="Nothing in this filter."
            />
            {selected ? (
              <>
                <p className="lg-section-label">Why this state</p>
                {detail.loading && !shown ? <p className="lg-empty">Loading observations…</p> : null}
                {detail.error ? (
                  <SectionStatus
                    loading={false}
                    error={detail.error}
                    hasData={false}
                    onRetry={detail.reload}
                    loadingText="Loading observations…"
                  />
                ) : null}
                {shown ? (
                  <ObservationSequence
                    marks={marks}
                    emptyText={emptyWindowSequence(selected)}
                    onSelect={(id) => {
                      setMarkId(id)
                    }}
                  />
                ) : null}
                <RuleList rows={whyRows(selected)} />
                <p className="lg-note">{shorten(selected.summary, 180)}</p>
              </>
            ) : null}
            {data.recent_failures.length > 0 ? (
              <>
                <p className="lg-section-label">Recent failures</p>
                <ul className="lg-links">
                  {data.recent_failures.slice(0, 5).map((item) => (
                    <li key={item.id}>
                      <a href={pageHref('failures')}>
                        {formatTime(item.occurred_at)} · {item.code}
                      </a>
                      <span className="lg-muted"> · {shorten(item.summary, 90)}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <p className="lg-section-label">This window</p>
            <OperationalList metrics={data.operational} />
            {selected ? (
              <div className="lg-mobile-action">
                <button type="button" className="lg-case-button" onClick={() => openCase(selected.integration_id)}>
                  Open support case
                </button>
              </div>
            ) : null}
          </div>
          <EvidenceTrail
            title={selected?.name ?? 'Evidence'}
            stations={stations}
            action={
              selected ? (
                <button type="button" className="lg-case-button" onClick={() => openCase(selected.integration_id)}>
                  Open support case
                </button>
              ) : null
            }
          />
        </div>
      ) : null}
      {draft ? <SupportCaseDrawer key={draft.title} draft={draft} onClose={closeDrawer} /> : null}
    </div>
  )
}

function useIntegrationDetail(id: string | null, windowHours: number) {
  const load = useCallback(
    () => (id ? getIntegrationReliability(id, windowHours) : Promise.reject(new Error('No integration'))),
    [id, windowHours],
  )
  return useResource(id ? load : null)
}

function marksForDetail(detail: IntegrationReliabilityDetail, markId: string | null): SequenceMark[] {
  if (detail.provider === 'instrumented_http') {
    return marksFromTelemetry(detail.recent_telemetry_events, { selectedId: markId })
  }
  if (detail.provider === 'stripe') {
    const start = Date.parse(detail.generated_at) - detail.window_hours * 3600_000
    const events = detail.recent_webhook_events.filter((event) => Date.parse(event.last_received_at) >= start)
    return marksFromWebhooks(events, markId)
  }
  return marksFromRequests(detail.recent_requests, markId)
}

function CountLamp({ count, state, label }: { count: number; state: HealthState; label: string }) {
  if (count === 0) return <span className="lg-count is-zero">0 {label}</span>
  return (
    <span className={`lg-health lg-health-${state === 'failed' ? 'bad' : 'warn'}`}>
      <span className={`lg-lamp ${state === 'failed' ? 'bad' : 'warn'}`} aria-hidden="true" />
      {count} {label}
    </span>
  )
}

function OperationalList({ metrics }: { metrics: OperationalMetrics }) {
  const rows: [string, number][] = [
    ['Real provider requests', metrics.real_provider_requests],
    ['Real provider errors', metrics.real_provider_errors],
    ['Simulated requests', metrics.simulated_requests],
    ['Failure Lab runs', metrics.failure_lab_runs],
    ['Webhook events received', metrics.webhook_events_received],
    ['Duplicate deliveries absorbed', metrics.duplicate_webhook_deliveries],
    ['Diagnostic runs', metrics.diagnostic_runs],
    ['Processed', metrics.webhook_processed],
    ['Pending', metrics.webhook_pending],
    ['Retry scheduled', metrics.webhook_retry_scheduled],
    ['Failed', metrics.webhook_failed],
    ['SDK-reported observations', metrics.sdk_reported_observations],
    ['SDK-reported errors', metrics.sdk_reported_errors],
  ]
  return (
    <>
      <dl className="lg-metrics">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className={ALERT_LABELS.has(label) && value > 0 ? 'lg-health-bad' : undefined}>{formatCount(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="lg-metric-note">SDK-reported counts are not included in real provider requests.</p>
    </>
  )
}

export default OverviewPage
