import type { ProviderRequestLog } from '../types'

interface ProviderRequestsTableProps {
  logs: ProviderRequestLog[]
}

function statusClass(statusCode: number | null): string {
  if (statusCode === null) return 'log-status-transport'
  if (statusCode >= 200 && statusCode < 300) return 'log-status-ok'
  if (
    statusCode === 401 ||
    statusCode === 403 ||
    statusCode === 429 ||
    (statusCode >= 400 && statusCode < 500)
  ) {
    return 'log-status-warn'
  }
  return 'log-status-error'
}

function ProviderRequestsTable({ logs }: ProviderRequestsTableProps) {
  if (logs.length === 0) {
    return <p className="empty-state">No provider requests logged yet.</p>
  }

  return (
    <div className="table-wrap">
      <table className="integrations-table">
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Provider</th>
            <th scope="col">Method</th>
            <th scope="col">Endpoint</th>
            <th scope="col">Status</th>
            <th scope="col">Latency</th>
            <th scope="col">Time</th>
            <th scope="col">Error</th>
            <th scope="col">Scenario</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              <td>
                <span className={`source-badge ${log.is_simulated ? 'source-simulated' : 'source-real'}`}>
                  {log.is_simulated ? 'Simulated' : 'Real'}
                </span>
              </td>
              <td>{log.provider}</td>
              <td>{log.method}</td>
              <td>{log.endpoint}</td>
              <td>
                <span className={`status-pill ${statusClass(log.status_code)}`}>
                  {log.status_code ?? 'transport'}
                </span>
              </td>
              <td>{log.latency_ms}ms</td>
              <td>{new Date(log.timestamp).toLocaleString()}</td>
              <td>{log.error_message ?? '—'}</td>
              <td>{log.scenario ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ProviderRequestsTable
