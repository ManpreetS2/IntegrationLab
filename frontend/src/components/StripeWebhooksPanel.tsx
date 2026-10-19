import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  apiOrigin,
  dismissWebhookEvent,
  getWebhookEvent,
  getWebhookSummary,
  listFailedWebhookEvents,
  listWebhookEvents,
  processDueWebhookEvents,
  processWebhookEvent,
  retryWebhookEvent,
} from '../api'
import EvidenceTrail from './ledger/EvidenceTrail'
import LedgerList, { LedgerFilters } from './ledger/LedgerList'
import { formatStripeAmount } from '../lib/stripeAmount'
import { formatTime } from '../format'
import { errorMessage } from '../hooks'
import { shorten, webhookFinding } from '../ledger/copy'
import type {
  Integration,
  WebhookEventDetail,
  WebhookEventSummary,
  WebhookProcessingStatus,
  WebhookSummary,
} from '../types'

interface StripeWebhooksPanelProps {
  integrations: Integration[]
}

const STATUS_OPTIONS: { id: WebhookProcessingStatus | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'processing', label: 'Processing' },
  { id: 'processed', label: 'Processed' },
  { id: 'retry_scheduled', label: 'Retry scheduled' },
  { id: 'failed', label: 'Failed' },
  { id: 'ignored', label: 'Ignored' },
  { id: 'dismissed', label: 'Dismissed' },
]

function statusLabel(status: string): string {
  return status.replaceAll('_', ' ')
}

interface WebhookSnapshot {
  summary: WebhookSummary
  events: WebhookEventSummary[]
  failed: WebhookEventSummary[]
}

async function loadSnapshot(status: WebhookProcessingStatus | ''): Promise<WebhookSnapshot> {
  const [summary, events, failed] = await Promise.all([
    getWebhookSummary(),
    listWebhookEvents({ status: status || undefined, limit: 50 }),
    listFailedWebhookEvents(25),
  ])
  return { summary, events, failed }
}

function loadErrorMessage(err: unknown): string {
  return errorMessage(err, 'Failed to load webhook events.')
}

function StripeWebhooksPanel({ integrations }: StripeWebhooksPanelProps) {
  const stripeIntegrations = useMemo(
    () => integrations.filter((item) => item.provider === 'stripe'),
    [integrations],
  )
  const [snapshot, setSnapshot] = useState<WebhookSnapshot | null>(null)
  const [statusFilter, setStatusFilter] = useState<WebhookProcessingStatus | ''>('')
  const [selected, setSelected] = useState<WebhookEventDetail | null>(null)
  const [pickedId, setPickedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const summary = snapshot?.summary ?? null
  const events = snapshot?.events ?? []
  const failed = snapshot?.failed ?? []

  useEffect(() => {
    let cancelled = false
    loadSnapshot(statusFilter)
      .then((next) => {
        if (!cancelled) setSnapshot(next)
      })
      .catch((err) => {
        if (!cancelled) setError(loadErrorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [statusFilter])

  const refresh = useCallback(async () => {
    try {
      setSnapshot(await loadSnapshot(statusFilter))
    } catch (err) {
      setError(loadErrorMessage(err))
    }
  }, [statusFilter])

  async function runAction(action: () => Promise<string | null>) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setNotice(await action())
      await refresh()
    } catch (err) {
      setError(errorMessage(err, 'Action failed.'))
    } finally {
      setBusy(false)
    }
  }

  function handleProcessDue() {
    void runAction(async () => {
      const counts = await processDueWebhookEvents(25)
      if (selected) setSelected(await getWebhookEvent(selected.id))
      return `Processed ${counts.processed} · retry scheduled ${counts.retry_scheduled} · failed ${counts.failed} · ignored ${counts.ignored}`
    })
  }

  function handleSelect(eventId: string) {
    setPickedId(eventId)
    void runAction(async () => {
      setSelected(await getWebhookEvent(eventId))
      return null
    })
  }

  function handleProcessOne(eventId: string) {
    void runAction(async () => {
      setSelected(await processWebhookEvent(eventId))
      return 'Processing attempt recorded.'
    })
  }

  function handleRetry(eventId: string) {
    void runAction(async () => {
      setSelected(await retryWebhookEvent(eventId))
      return 'Event queued for a new retry cycle.'
    })
  }

  function handleDismiss(event: WebhookEventSummary) {
    const confirmed = window.confirm(
      `Dismiss ${event.event_type} (${event.provider_event_id})? It will stop being processed. History is kept.`,
    )
    if (!confirmed) return
    void runAction(async () => {
      setSelected(await dismissWebhookEvent(event.id))
      return 'Event dismissed.'
    })
  }

  const detail = selected?.id === pickedId ? selected : null
  const summaryRow = events.find((item) => item.id === pickedId) ?? failed.find((item) => item.id === pickedId) ?? null
  const canProcess = detail?.processing_status === 'pending' || detail?.processing_status === 'retry_scheduled'
  const canRetry = detail?.processing_status === 'failed'

  return (
    <div className={busy ? 'lg-busy' : undefined} aria-busy={busy || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker">Webhooks · test mode</p>
          <h1 className="lg-finding">{webhookFinding(summary)}</h1>
          <p className="lg-note">
            Deliveries are verified and stored first, then processed with bounded retries. Receiving an event is not the
            same as processing it. The failed queue is persistent and is not a count of deliveries in a time window.
          </p>
          {stripeIntegrations.length > 0 ? (
            stripeIntegrations.map((item) => (
              <p key={item.id} className="lg-mono">
                {item.name} · {`${apiOrigin()}/webhooks/stripe/${item.id}`}
              </p>
            ))
          ) : (
            <p className="lg-note">Create a Stripe integration to get a webhook endpoint.</p>
          )}
          {summary ? (
            <dl className="lg-metrics">
              <div>
                <dt>Received</dt>
                <dd>{summary.received}</dd>
              </div>
              <div>
                <dt>Pending</dt>
                <dd>{summary.pending}</dd>
              </div>
              <div>
                <dt>Processed</dt>
                <dd>{summary.processed}</dd>
              </div>
              <div>
                <dt>Retry scheduled</dt>
                <dd>{summary.retry_scheduled}</dd>
              </div>
              <div>
                <dt>Failed queue</dt>
                <dd className={summary.failed > 0 ? 'lg-health-bad' : undefined}>{summary.failed}</dd>
              </div>
              <div>
                <dt>Duplicates absorbed</dt>
                <dd>{summary.duplicate_deliveries}</dd>
              </div>
            </dl>
          ) : null}
          <div className="lg-toolbar">
            <LedgerFilters
              label="Status"
              value={statusFilter || 'all'}
              onChange={(id) => setStatusFilter(id === 'all' ? '' : (id as WebhookProcessingStatus))}
              options={STATUS_OPTIONS}
            />
            <button type="button" className="lg-case-button" onClick={handleProcessDue} disabled={busy}>
              {busy ? 'Working…' : 'Process due events'}
            </button>
          </div>
          {notice ? <p className="lg-note">{notice}</p> : null}
          {error ? (
            <p className="error-text" role="alert">
              {error}
            </p>
          ) : null}
          {!snapshot ? <p className="lg-empty">Loading webhook events…</p> : null}
          {snapshot && events.length === 0 ? (
            <p className="lg-empty">No webhook events match this status.</p>
          ) : null}
          {events.length > 0 ? (
            <LedgerList
              label="Webhook events"
              columns={['Received', 'Event', 'Status', 'Attempts']}
              rows={events.map((event) => ({
                id: event.id,
                title: event.event_type,
                meta: statusLabel(event.processing_status),
                detail: event.last_error_code ?? event.provider_object_id ?? '—',
                cells: [
                  formatTime(event.first_received_at),
                  <span key="type" className="lg-mono">
                    {event.event_type}
                  </span>,
                  statusLabel(event.processing_status),
                  String(event.attempt_count),
                ],
              }))}
              selectedId={pickedId}
              onSelect={handleSelect}
              emptyText="No webhook events match this status."
            />
          ) : null}
          <p className="lg-section-label">Failed queue</p>
          <p className="lg-note">These events stay failed until they are retried or dismissed. They are not new deliveries.</p>
          {snapshot && failed.length === 0 ? <p className="lg-empty">No failed events.</p> : null}
          {failed.length > 0 ? (
            <LedgerList
              label="Failed events"
              columns={['Failed', 'Event', 'Attempts', 'Last error']}
              rows={failed.map((event) => ({
                id: event.id,
                title: event.event_type,
                meta: 'Failed',
                detail: event.last_error_code ?? '—',
                cells: [
                  formatTime(event.failed_at),
                  event.event_type,
                  String(event.attempt_count),
                  event.last_error_code ?? '—',
                ],
              }))}
              selectedId={pickedId}
              onSelect={handleSelect}
              emptyText="No failed events."
            />
          ) : null}
          {selected && selected.effects.length > 0 ? (
            <p className="lg-note">
              Effects applied once: {selected.effects.map((effect) => effect.effect_type).join(', ')}
            </p>
          ) : null}
          {selected && selected.attempts.length > 0 ? (
            <>
              <p className="lg-section-label">Attempts</p>
              <ul className="lg-links">
                {selected.attempts.map((attempt) => (
                  <li key={attempt.id}>
                    Attempt {attempt.attempt_number}
                    {attempt.retry_cycle > 1 ? ` · cycle ${attempt.retry_cycle}` : ''} · {attempt.outcome}
                    {attempt.manual ? ' · manual' : ''}
                    {attempt.error_code ? ` · ${attempt.error_code}` : ''}
                    <span className="lg-muted"> · {formatTime(attempt.started_at)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
        <EvidenceTrail
          title={detail?.event_type ?? summaryRow?.event_type ?? 'Delivery'}
          stations={eventStations(detail)}
          action={
            detail ? (
              <div className="lg-form-row">
                {canProcess ? (
                  <button type="button" className="lg-case-button" disabled={busy} onClick={() => handleProcessOne(detail.id)}>
                    Process now
                  </button>
                ) : null}
                {canRetry ? (
                  <button type="button" className="lg-case-button" disabled={busy} onClick={() => handleRetry(detail.id)}>
                    Retry
                  </button>
                ) : null}
                {canRetry ? (
                  <button type="button" className="secondary-button" disabled={busy} onClick={() => handleDismiss(detail)}>
                    Dismiss
                  </button>
                ) : null}
              </div>
            ) : null
          }
        />
      </div>
    </div>
  )
}

function eventStations(selected: WebhookEventDetail | null) {
  if (!selected) {
    return [{ label: 'Event', text: 'Select a delivery or a failed-queue row. Actions apply to the selected event.' }]
  }
  const extra = Math.max(0, selected.delivery_count - 1)
  return [
    { label: 'Status', text: `${statusLabel(selected.processing_status)} · signature ${selected.signature_verified ? 'verified' : 'not verified'}` },
    { label: 'Object', text: selected.provider_object_id ?? 'No object id' },
    { label: 'Amount', text: formatStripeAmount(selected.amount, selected.currency) },
    {
      label: 'Delivery',
      text: extra > 0 ? `${extra} extra ${extra === 1 ? 'delivery' : 'deliveries'} absorbed` : 'One delivery stored',
    },
    { label: 'Last error', text: shorten(selected.last_error_message ?? selected.last_error_code ?? 'None recorded', 160) },
  ]
}

export default StripeWebhooksPanel
