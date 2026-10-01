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

const STATUS_OPTIONS: WebhookProcessingStatus[] = [
  'pending',
  'processing',
  'processed',
  'retry_scheduled',
  'failed',
  'ignored',
  'dismissed',
]

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—'
}

function formatAmount(amount: number | null, currency: string | null): string {
  if (amount === null || currency === null) return '—'
  return `${(amount / 100).toFixed(2)} ${currency.toUpperCase()}`
}

function statusLabel(status: string): string {
  return status.replace('_', ' ')
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
  return err instanceof Error ? err.message : 'Failed to load webhook events.'
}

function StripeWebhooksPanel({ integrations }: StripeWebhooksPanelProps) {
  const stripeIntegrations = useMemo(
    () => integrations.filter((item) => item.provider === 'stripe'),
    [integrations],
  )

  const [snapshot, setSnapshot] = useState<WebhookSnapshot | null>(null)
  const [statusFilter, setStatusFilter] = useState<WebhookProcessingStatus | ''>('')
  const [selected, setSelected] = useState<WebhookEventDetail | null>(null)
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
      setError(err instanceof Error ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  function handleProcessDue() {
    void runAction(async () => {
      const counts = await processDueWebhookEvents(25)
      if (selected) setSelected(await getWebhookEvent(selected.id))
      return (
        `Processed: ${counts.processed} · Retry scheduled: ${counts.retry_scheduled} · ` +
        `Failed: ${counts.failed} · Ignored: ${counts.ignored}`
      )
    })
  }

  function handleSelect(eventId: string) {
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
      `Dismiss ${event.event_type} (${event.provider_event_id})? It will stop being processed; history is kept.`,
    )
    if (!confirmed) return
    void runAction(async () => {
      setSelected(await dismissWebhookEvent(event.id))
      return 'Event dismissed.'
    })
  }

  const cards: { label: string; value: number | undefined }[] = [
    { label: 'Received', value: summary?.received },
    { label: 'Pending', value: summary?.pending },
    { label: 'Processed', value: summary?.processed },
    { label: 'Retry scheduled', value: summary?.retry_scheduled },
    { label: 'Failed', value: summary?.failed },
  ]

  const canProcessSelected =
    selected?.processing_status === 'pending' || selected?.processing_status === 'retry_scheduled'

  return (
    <div className="webhooks">
      <p className="muted">
        Stripe deliveries are verified and stored first (quick 2xx), then processed separately with
        bounded retries. Receiving an event is not the same as processing it successfully.
      </p>

      {stripeIntegrations.length > 0 ? (
        <div className="webhook-endpoints">
          {stripeIntegrations.map((item) => (
            <p key={item.id} className="muted">
              {item.name} endpoint: <code>{`${apiOrigin()}/webhooks/stripe/${item.id}`}</code>
            </p>
          ))}
        </div>
      ) : (
        <p className="muted">Create a Stripe integration to get a webhook endpoint.</p>
      )}

      <div className="summary-grid webhook-summary">
        {cards.map((card) => (
          <article key={card.label} className="summary-card">
            <p className="summary-label">{card.label}</p>
            <p className="summary-value">{card.value ?? '—'}</p>
          </article>
        ))}
      </div>
      {summary && summary.duplicate_deliveries > 0 ? (
        <p className="muted">Duplicate deliveries absorbed: {summary.duplicate_deliveries}</p>
      ) : null}

      <div className="webhook-toolbar">
        <label>
          Status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as WebhookProcessingStatus | '')}
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={handleProcessDue} disabled={busy}>
          {busy ? 'Working…' : 'Process due events'}
        </button>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={busy}>
          Refresh
        </button>
      </div>

      {notice ? <p className="success-text">{notice}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      {events.length === 0 ? (
        <p className="empty-state">
          No webhook events yet. Forward test events with the Stripe CLI (see docs/stripe-webhooks.md).
        </p>
      ) : (
        <div className="table-wrap">
          <table className="integrations-table">
            <thead>
              <tr>
                <th scope="col">Received</th>
                <th scope="col">Event type</th>
                <th scope="col">Object</th>
                <th scope="col">Delivery count</th>
                <th scope="col">Status</th>
                <th scope="col">Attempts</th>
                <th scope="col">Next attempt</th>
                <th scope="col">Last error</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>
                    <button type="button" className="linkish-button" onClick={() => handleSelect(event.id)}>
                      {formatTime(event.first_received_at)}
                    </button>
                  </td>
                  <td>{event.event_type}</td>
                  <td>{event.provider_object_id ?? '—'}</td>
                  <td>{event.delivery_count}</td>
                  <td>
                    <span className={`webhook-status webhook-status-${event.processing_status}`}>
                      {statusLabel(event.processing_status)}
                    </span>
                  </td>
                  <td>{event.attempt_count}</td>
                  <td>{formatTime(event.next_attempt_at)}</td>
                  <td>{event.last_error_code ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <div className="webhook-detail">
          <div className="panel-header">
            <h3>
              {selected.event_type} <span className="muted">{selected.provider_event_id}</span>
            </h3>
            <div className="github-actions">
              {canProcessSelected ? (
                <button type="button" onClick={() => handleProcessOne(selected.id)} disabled={busy}>
                  Process now
                </button>
              ) : null}
              <button type="button" className="secondary-button" onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
          </div>

          <dl className="result-grid webhook-detail-grid">
            <div>
              <dt>Status</dt>
              <dd>
                <span className={`webhook-status webhook-status-${selected.processing_status}`}>
                  {statusLabel(selected.processing_status)}
                </span>
              </dd>
            </div>
            <div>
              <dt>Signature</dt>
              <dd>{selected.signature_verified ? 'Verified' : 'Not verified'}</dd>
            </div>
            <div>
              <dt>Object</dt>
              <dd>{selected.provider_object_id ?? '—'}</dd>
            </div>
            <div>
              <dt>Amount</dt>
              <dd>{formatAmount(selected.amount, selected.currency)}</dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>{selected.livemode === null ? '—' : selected.livemode ? 'Live' : 'Test'}</dd>
            </div>
            <div>
              <dt>Duplicate deliveries</dt>
              <dd>Duplicate deliveries: {selected.delivery_count - 1}</dd>
            </div>
            <div>
              <dt>Retry cycle</dt>
              <dd>
                {selected.retry_cycle} (attempt {selected.cycle_attempt_count} of {selected.max_attempts})
              </dd>
            </div>
            <div>
              <dt>Manual retries</dt>
              <dd>{selected.manual_retry_count}</dd>
            </div>
            <div>
              <dt>First / last received</dt>
              <dd>
                {formatTime(selected.first_received_at)} / {formatTime(selected.last_received_at)}
              </dd>
            </div>
          </dl>

          <h4>Effects</h4>
          {selected.effects.length === 0 ? (
            <p className="empty-state">No effect applied.</p>
          ) : (
            <ul className="webhook-effects">
              {selected.effects.map((effect) => (
                <li key={effect.id}>
                  <strong>{effect.effect_type}</strong> — applied once at {formatTime(effect.applied_at)}
                  {effect.summary ? <span className="muted"> · {effect.summary}</span> : null}
                </li>
              ))}
            </ul>
          )}

          <h4>Attempt timeline</h4>
          {selected.attempts.length === 0 ? (
            <p className="empty-state">Not attempted yet.</p>
          ) : (
            <ol className="webhook-timeline">
              {selected.attempts.map((attempt) => (
                <li key={attempt.id} className={`timeline-${attempt.outcome}`}>
                  <strong>
                    Attempt {attempt.attempt_number}
                    {attempt.retry_cycle > 1 ? ` (cycle ${attempt.retry_cycle})` : ''}
                  </strong>{' '}
                  {attempt.outcome}
                  {attempt.manual ? ' · manual' : ''}
                  {attempt.error_code ? ` · ${attempt.error_code}` : ''}
                  {attempt.scheduled_delay_seconds !== null
                    ? ` · retry scheduled in ${attempt.scheduled_delay_seconds}s`
                    : ''}
                  <span className="muted"> · {formatTime(attempt.started_at)}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : null}

      <div className="webhook-failed">
        <h3>Failed events</h3>
        {failed.length === 0 ? (
          <p className="empty-state">No failed events.</p>
        ) : (
          <div className="table-wrap">
            <table className="integrations-table">
              <thead>
                <tr>
                  <th scope="col">Failed at</th>
                  <th scope="col">Event type</th>
                  <th scope="col">Object</th>
                  <th scope="col">Attempts</th>
                  <th scope="col">Last error</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {failed.map((event) => (
                  <tr key={event.id}>
                    <td>
                      <button type="button" className="linkish-button" onClick={() => handleSelect(event.id)}>
                        {formatTime(event.failed_at)}
                      </button>
                    </td>
                    <td>{event.event_type}</td>
                    <td>{event.provider_object_id ?? '—'}</td>
                    <td>{event.attempt_count}</td>
                    <td>
                      {event.last_error_code ?? '—'}
                      {event.last_error_message ? (
                        <span className="muted"> · {event.last_error_message}</span>
                      ) : null}
                    </td>
                    <td>
                      <div className="github-actions">
                        <button type="button" onClick={() => handleRetry(event.id)} disabled={busy}>
                          Retry
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => handleDismiss(event)}
                          disabled={busy}
                        >
                          Dismiss
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default StripeWebhooksPanel
