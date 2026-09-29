import { formatTime, SOURCE_LABELS } from '../format'
import { pageHref } from '../hooks'
import type { FailureItem } from '../types'
import { SeverityBadge } from './StatusBadges'

interface FailuresTableProps {
  items: FailureItem[]
  emptyText: string
}

function context(item: FailureItem): string {
  if (item.source === 'webhook_processing') {
    return [item.event_type, item.attempt_count !== null ? `${item.attempt_count} attempt(s)` : null]
      .filter(Boolean)
      .join(' · ')
  }
  if (item.endpoint) {
    const status = item.status_code !== null ? `HTTP ${item.status_code}` : 'no response'
    const latency = item.latency_ms !== null ? ` · ${item.latency_ms} ms` : ''
    return `${item.method ?? ''} ${item.endpoint} · ${status}${latency}`.trim()
  }
  return '—'
}

function FailuresTable({ items, emptyText }: FailuresTableProps) {
  if (items.length === 0) return <p className="empty-state">{emptyText}</p>

  return (
    <div className="table-wrap">
      <table className="integrations-table failures-table">
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Severity</th>
            <th scope="col">Source</th>
            <th scope="col">Integration</th>
            <th scope="col">Code</th>
            <th scope="col">Summary</th>
            <th scope="col">Context</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="nowrap">{formatTime(item.occurred_at)}</td>
              <td>
                <SeverityBadge severity={item.severity} />
              </td>
              <td>
                {item.simulated ? (
                  <span className="source-badge source-simulated">Simulation</span>
                ) : (
                  SOURCE_LABELS[item.source]
                )}
              </td>
              <td>{item.integration_name ?? item.provider}</td>
              <td>
                <code>{item.code}</code>
              </td>
              <td>
                {item.summary}
                {item.diagnostic_run_id && item.integration_id ? (
                  <>
                    {' '}
                    <a href={pageHref('diagnostics', { integration: item.integration_id })}>View run</a>
                  </>
                ) : null}
              </td>
              <td className="muted">{context(item)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default FailuresTable
