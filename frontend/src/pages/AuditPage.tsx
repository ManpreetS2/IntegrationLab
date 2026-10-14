import { useCallback, useState } from 'react'
import { listAuditEvents } from '../api'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import IdentifierText from '../components/ledger/IdentifierText'
import LedgerList from '../components/ledger/LedgerList'
import SectionStatus from '../components/SectionStatus'
import { formatTime } from '../format'
import { useResource } from '../hooks'
import { shorten } from '../ledger/copy'
import type { OperatorAuditEvent } from '../types'

function shortCorr(id: string | null): string {
  if (!id) return '—'
  return `corr_${id.replace(/-/g, '').slice(0, 4)}…`
}

function AuditPage() {
  const [action, setAction] = useState('')
  const [correlationId, setCorrelationId] = useState('')
  const [pickedId, setPickedId] = useState<string | null>(null)

  const load = useCallback(
    () =>
      listAuditEvents({
        action: action || undefined,
        correlation_id: correlationId || undefined,
        limit: 100,
      }),
    [action, correlationId],
  )
  const events = useResource(load)
  const rows = events.data ?? []
  const selected = rows.find((item) => item.id === pickedId) ?? rows[0] ?? null
  const finding = !events.data
    ? 'Audit'
    : rows.length === 0
      ? 'No operator events match these filters.'
      : rows.length === 1
        ? 'One operator event.'
        : `${rows.length} operator events.`

  return (
    <div className={events.loading ? 'lg-busy' : undefined} aria-busy={events.loading || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker">
            Audit
            {events.loading && events.data ? <span className="lg-refresh">Refreshing…</span> : null}
          </p>
          <h1 className="lg-finding">{finding}</h1>
          <p className="lg-note">Append-only operator and system events. Secrets and raw payloads are not stored here.</p>
          <div className="lg-form-row">
            <label className="lg-field">
              Action
              <input value={action} onChange={(event) => setAction(event.target.value)} placeholder="support_case_created" />
            </label>
            <label className="lg-field">
              Correlation ID
              <input
                value={correlationId}
                onChange={(event) => setCorrelationId(event.target.value)}
                placeholder="full UUID"
              />
            </label>
          </div>
          <SectionStatus
            loading={events.loading}
            error={events.error}
            hasData={Boolean(events.data)}
            onRetry={events.reload}
            loadingText="Loading audit events…"
          />
          {events.data ? (
            <LedgerList
              label="Audit events"
              columns={['When', 'Action', 'Target', 'Result']}
              rows={rows.map((item) => ({
                id: item.id,
                title: item.action,
                meta: item.outcome,
                detail: shorten(item.safe_summary, 90),
                cells: [
                  formatTime(item.created_at),
                  <span key="action" className="lg-id">
                    <IdentifierText value={item.action} />
                  </span>,
                  item.target_type,
                  item.outcome,
                ],
              }))}
              selectedId={selected?.id ?? null}
              onSelect={setPickedId}
              emptyText="No operator events match these filters."
            />
          ) : null}
        </div>
        <EvidenceTrail title={selected?.action ?? 'Event'} stations={auditStations(selected)} identifier />
      </div>
    </div>
  )
}

function auditStations(item: OperatorAuditEvent | null) {
  if (!item) return [{ label: 'Record', text: 'Select an event. The summary is the stored safe text.' }]
  return [
    { label: 'Summary', text: shorten(item.safe_summary, 180) },
    { label: 'Target', text: `${item.target_type}${item.target_id ? ` · ${item.target_id.slice(0, 8)}` : ''}` },
    { label: 'Actor', text: item.actor_type },
    { label: 'Correlation', text: item.correlation_id ? `${shortCorr(item.correlation_id)} · ${item.correlation_id}` : 'None' },
    { label: 'Result', text: item.outcome },
  ].slice(0, 5)
}

export default AuditPage
