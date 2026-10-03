import { useCallback, useState } from 'react'
import { listAuditEvents } from '../api'
import SectionStatus from '../components/SectionStatus'
import { useResource } from '../hooks'

function shortCorr(id: string | null): string {
  if (!id) return '—'
  return `corr_${id.replace(/-/g, '').slice(0, 4)}…`
}

function AuditPage() {
  const [action, setAction] = useState('')
  const [correlationId, setCorrelationId] = useState('')

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

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Operator audit</h2>
        <button type="button" className="secondary-button" onClick={events.reload}>
          Refresh
        </button>
      </div>
      <p className="muted">
        Append-only record of meaningful operator actions. Secrets and raw payloads are never stored here.
      </p>
      <div className="filter-row webhook-toolbar">
        <label>
          Action
          <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="support_case_created" />
        </label>
        <label>
          Correlation ID
          <input
            value={correlationId}
            onChange={(e) => setCorrelationId(e.target.value)}
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
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Target</th>
                <th>Summary</th>
                <th>Correlation</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((row) => (
                <tr key={row.id}>
                  <td>{new Date(row.created_at).toLocaleString()}</td>
                  <td>{row.action}</td>
                  <td>
                    {row.target_type}
                    {row.target_id ? <div className="muted">{row.target_id.slice(0, 8)}…</div> : null}
                  </td>
                  <td>{row.safe_summary}</td>
                  <td title={row.correlation_id ?? undefined}>{shortCorr(row.correlation_id)}</td>
                  <td>{row.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

export default AuditPage
