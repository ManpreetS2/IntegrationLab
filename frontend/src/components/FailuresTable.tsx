import { useState } from 'react'
import { createSupportCase } from '../api'
import { formatTime, SOURCE_LABELS } from '../format'
import { errorMessage, navigate, pageHref } from '../hooks'
import type { EvidenceType, FailureItem, FailureSource } from '../types'
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

function evidenceFor(item: FailureItem): { type: EvidenceType; id: string } | null {
  if (item.source === 'failure_lab' && item.id.startsWith('failure_lab:')) {
    return { type: 'failure_lab_run', id: item.id.slice('failure_lab:'.length) }
  }
  if (item.source === 'diagnostic' && item.diagnostic_run_id) {
    return { type: 'diagnostic_run', id: item.diagnostic_run_id }
  }
  if (item.source === 'webhook_processing' && item.webhook_event_id) {
    return { type: 'webhook_event', id: item.webhook_event_id }
  }
  if (item.source === 'provider_request' && item.id) {
    const id = item.id.includes(':') ? item.id.split(':').pop()! : item.id
    return { type: 'provider_request', id }
  }
  return null
}

function titleFor(item: FailureItem): string {
  if (item.simulated) return `Simulated failure: ${item.code}`
  if (item.source === 'provider_request' && item.status_code === 401) {
    return 'GitHub authentication failure observed'
  }
  return `${SOURCE_LABELS[item.source as FailureSource] ?? item.source}: ${item.code}`
}

function FailuresTable({ items, emptyText }: FailuresTableProps) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (items.length === 0) return <p className="empty-state">{emptyText}</p>

  async function openCase(item: FailureItem) {
    if (!item.integration_id) {
      setError('Failure is missing an integration id.')
      return
    }
    const evidence = evidenceFor(item)
    setBusyId(item.id)
    setError(null)
    try {
      const created = await createSupportCase({
        integration_id: item.integration_id,
        title: titleFor(item),
        severity:
          item.severity === 'critical' ? 'SEV1' : item.severity === 'error' ? 'SEV2' : item.severity === 'warning' ? 'SEV3' : 'SEV4',
        impact_summary: item.summary,
        suspected_cause: item.simulated
          ? 'Failure Lab simulation evidence (not a live incident claim).'
          : item.summary,
        source_evidence_type: evidence?.type,
        source_evidence_id: evidence?.id,
      })
      navigate('support', { case: created.id })
    } catch (err) {
      setError(errorMessage(err, 'Unable to create support case.'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      {error ? <p className="banner banner-error">{error}</p> : null}
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
              <th scope="col">Actions</th>
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
                <td>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!item.integration_id || busyId === item.id}
                    onClick={() => openCase(item)}
                  >
                    Create Support Case
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export default FailuresTable
