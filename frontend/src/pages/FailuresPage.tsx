import { useCallback, useState } from 'react'
import { getIntegrationReliability, listReliabilityFailures } from '../api'
import FailureLabPanel from '../components/FailureLabPanel'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import LedgerList, { LedgerFilters } from '../components/ledger/LedgerList'
import ObservationSequence from '../components/ledger/ObservationSequence'
import SupportCaseDrawer from '../components/ledger/SupportCaseDrawer'
import SectionStatus from '../components/SectionStatus'
import { formatTime, SEVERITY_LABELS, SOURCE_LABELS } from '../format'
import { useResource } from '../hooks'
import { draftFromFailure, type CaseDraft } from '../ledger/case'
import { failureFinding, shorten } from '../ledger/copy'
import {
  marksFromRequests,
  marksFromTelemetry,
  marksFromWebhooks,
  sequenceFocusForFailure,
  type SequenceMark,
} from '../ledger/sequence'
import { failureStations } from '../ledger/trail'
import { recordForSelection } from '../viewSelection'
import type { FailureSource, Integration, IntegrationProvider, IntegrationReliabilityDetail } from '../types'

type FailureFilter = 'all' | 'github' | 'stripe' | 'sdk_telemetry' | 'failure_lab' | 'diagnostic'

const FILTERS: { id: FailureFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'github', label: 'GitHub API' },
  { id: 'stripe', label: 'Stripe processing' },
  { id: 'sdk_telemetry', label: 'SDK-reported' },
  { id: 'diagnostic', label: 'Diagnostics' },
  { id: 'failure_lab', label: 'Failure Lab' },
]

const FILTER_PARAMS: Record<FailureFilter, { provider?: IntegrationProvider; source?: FailureSource }> = {
  all: {},
  github: { provider: 'github', source: 'provider_request' },
  stripe: { provider: 'stripe', source: 'webhook_processing' },
  sdk_telemetry: { provider: 'instrumented_http', source: 'sdk_telemetry' },
  diagnostic: { source: 'diagnostic' },
  failure_lab: { source: 'failure_lab' },
}

function FailuresPage({
  integrations,
  onIntegrationsChanged,
}: {
  integrations: Integration[]
  onIntegrationsChanged: () => void
}) {
  const [filter, setFilter] = useState<FailureFilter>('all')
  const [includeSimulated, setIncludeSimulated] = useState(false)
  const [windowHours, setWindowHours] = useState(24)
  const [pickedId, setPickedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<CaseDraft | null>(null)
  const closeDrawer = useCallback(() => setDraft(null), [])

  const loadFailures = useCallback(
    () =>
      listReliabilityFailures({
        ...FILTER_PARAMS[filter],
        include_simulated: filter === 'all' ? includeSimulated : undefined,
        window_hours: windowHours,
        limit: 100,
      }),
    [filter, includeSimulated, windowHours],
  )
  const failures = useResource(loadFailures)
  const items = failures.data ?? []
  const selected =
    items.find((item) => item.id === pickedId) ??
    (pickedId === null ? (items[0] ?? null) : (items[0] ?? null))

  const selectedIntegrationId = selected?.integration_id ?? null
  const loadDetail = useCallback(
    () =>
      selectedIntegrationId
        ? getIntegrationReliability(selectedIntegrationId, windowHours)
        : Promise.reject(new Error('No integration')),
    [selectedIntegrationId, windowHours],
  )
  const detail = useResource(selectedIntegrationId ? loadDetail : null)
  const loadedDetail = recordForSelection(selected?.integration_id, detail.data)
  const shown = loadedDetail?.window_hours === windowHours ? loadedDetail : undefined
  const focus = selected ? sequenceFocusForFailure(selected) : { kind: 'none' as const, id: null }
  const marks = shown && focus.kind !== 'none' ? marksForFailure(shown, focus) : []
  const highlighted = focus.id ? marks.some((mark) => mark.id === focus.id) : false

  function openCase(id: string) {
    const item = items.find((entry) => entry.id === id)
    if (!item) return
    setPickedId(item.id)
    const environment = integrations.find((entry) => entry.id === item.integration_id)?.environment
    const next = draftFromFailure(item, environment)
    if (next) setDraft(next)
  }

  return (
    <div className={failures.loading ? 'lg-busy' : undefined} aria-busy={failures.loading || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker" role="status">
            Failure investigation · last {windowHours}h
            {failures.loading ? <span className="lg-refresh">Refreshing…</span> : null}
          </p>
          <h1 className="lg-finding">{failures.data ? failureFinding(selected, items.length) : 'Failures'}</h1>
          {selected ? <p className="lg-status">{shorten(selected.summary, 180)}</p> : null}
          <div className="lg-toolbar">
            <LedgerFilters
              label="Failure source"
              value={filter}
              onChange={(id) => {
                setFilter(id as FailureFilter)
                setPickedId(null)
              }}
              options={FILTERS}
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
            {filter === 'all' ? (
              <label className="lg-inline-check">
                <input
                  type="checkbox"
                  checked={includeSimulated}
                  onChange={(event) => setIncludeSimulated(event.target.checked)}
                />
                Include simulations
              </label>
            ) : null}
          </div>
          <SectionStatus
            loading={failures.loading}
            error={failures.error}
            hasData={Boolean(failures.data)}
            onRetry={failures.reload}
            loadingText="Loading failures…"
          />
          {failures.data ? (
            <LedgerList
              label="Failures"
              columns={['When', 'Severity', 'Source', 'Code']}
              rows={items.map((item) => ({
                id: item.id,
                title: item.code,
                meta: item.simulated ? 'Simulation' : SOURCE_LABELS[item.source],
                detail: shorten(item.summary, 90),
                cells: [
                  formatTime(item.occurred_at),
                  SEVERITY_LABELS[item.severity],
                  item.simulated ? 'Simulation' : SOURCE_LABELS[item.source],
                  <span key="code" className="lg-mono">
                    {item.code}
                  </span>,
                ],
              }))}
              selectedId={selected?.id ?? null}
              onSelect={setPickedId}
              onOpen={openCase}
              emptyText={
                filter === 'failure_lab'
                  ? 'No Failure Lab simulations in this window.'
                  : 'No failures match these filters.'
              }
            />
          ) : null}
          {selected && focus.kind === 'none' ? (
            <p className="lg-note">Diagnostics and simulations are not drawn as an observation sequence.</p>
          ) : null}
          {selected && focus.kind !== 'none' ? (
            <>
              <SectionStatus
                loading={detail.loading}
                error={detail.error}
                hasData={Boolean(shown)}
                onRetry={detail.reload}
                loadingText="Loading observations…"
              />
              {shown ? <ObservationSequence marks={marks} /> : null}
              {shown && focus.id && !highlighted ? (
                <p className="lg-note">The selected failure is outside the latest returned sequence.</p>
              ) : null}
            </>
          ) : null}
          {selected?.integration_id ? (
            <div className="lg-mobile-action">
              <button type="button" className="lg-case-button" onClick={() => openCase(selected.id)}>
                Open support case
              </button>
            </div>
          ) : null}
          <section className="lg-lab">
            <p className="lg-section-label">Failure Lab</p>
            <p className="lg-note">
              Sandboxed scenarios. Results are labeled simulated, excluded from health and real metrics, and never
              change a real connection.
            </p>
            <FailureLabPanel
              integrations={integrations}
              onCompleted={() => {
                failures.reload()
                onIntegrationsChanged()
              }}
            />
          </section>
        </div>
        <EvidenceTrail
          title={selected ? 'Evidence' : 'No failure selected'}
          stations={selected ? failureStations(selected) : []}
          action={
            selected?.integration_id ? (
              <button type="button" className="lg-case-button" onClick={() => openCase(selected.id)}>
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

function marksForFailure(
  detail: IntegrationReliabilityDetail,
  focus: { kind: 'telemetry' | 'webhook' | 'request' | 'none'; id: string | null },
): SequenceMark[] {
  if (focus.kind === 'telemetry') return marksFromTelemetry(detail.recent_telemetry_events, { selectedId: focus.id })
  if (focus.kind === 'webhook') {
    const start = Date.parse(detail.generated_at) - detail.window_hours * 3600_000
    const events = detail.recent_webhook_events.filter((event) => Date.parse(event.last_received_at) >= start)
    return marksFromWebhooks(events, focus.id)
  }
  if (focus.kind === 'request') return marksFromRequests(detail.recent_requests, focus.id)
  return []
}

export default FailuresPage
