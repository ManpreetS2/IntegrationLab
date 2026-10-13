import { formatIntegrationStatus, formatProvider } from '../format'
import { pageHref } from '../hooks'
import type { Integration } from '../types'

interface IntegrationsTableProps {
  integrations: Integration[]
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Never'
  }

  return new Date(value).toLocaleString()
}

function IntegrationsTable({ integrations }: IntegrationsTableProps) {
  if (integrations.length === 0) {
    return <p className="empty-state">No integrations yet. Create one below.</p>
  }

  return (
    <div className="table-wrap">
      <table className="integrations-table">
        <thead>
          <tr>
            <th scope="col">Provider</th>
            <th scope="col">Integration name</th>
            <th scope="col">Status</th>
            <th scope="col">Last checked</th>
          </tr>
        </thead>
        <tbody>
          {integrations.map((integration) => (
            <tr key={integration.id}>
              <td className="provider-cell">{formatProvider(integration.provider)}</td>
              <td>
                {integration.provider === 'instrumented_http' ? (
                  <a href={pageHref('telemetry', { integration: integration.id })}>{integration.name}</a>
                ) : (
                  integration.name
                )}
              </td>
              <td>
                <span className={`status-pill status-${integration.status}`}>
                  {formatIntegrationStatus(integration.status)}
                </span>
              </td>
              <td>{formatTimestamp(integration.last_checked_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default IntegrationsTable
