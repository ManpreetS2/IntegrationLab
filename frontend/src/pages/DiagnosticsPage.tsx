import { useCallback, useState } from 'react'
import { getDiagnosticRun, getIntegrationReliability, listDiagnosticRuns, runDiagnostics } from '../api'
import SectionStatus from '../components/SectionStatus'
import { CheckBadge, HealthBadge } from '../components/StatusBadges'
import { formatMs, formatTime } from '../format'
import { errorMessage, navigate, useResource } from '../hooks'
import type { DiagnosticRun, Integration } from '../types'

interface DiagnosticsPageProps {
  integrations: Integration[]
  requestedIntegrationId: string | null
}

function ChecksTable({ run }: { run: DiagnosticRun }) {
  return (
    <div className="table-wrap">
      <table className="integrations-table checks-table">
        <thead>
          <tr>
            <th scope="col">Status</th>
            <th scope="col">Check</th>
            <th scope="col">Evidence</th>
            <th scope="col">Recommendation</th>
            <th scope="col">Latency</th>
          </tr>
        </thead>
        <tbody>
          {run.checks.map((check) => (
            <tr key={check.check_code}>
              <td>
                <CheckBadge status={check.status} />
              </td>
              <td>
                <strong>{check.title}</strong>
                {check.required ? <span className="required-tag">Required</span> : null}
                <div className="muted small-text">
                  <code>{check.check_code}</code>
                </div>
              </td>
              <td>{check.evidence}</td>
              <td>{check.recommendation ?? '—'}</td>
              <td className="nowrap">{formatMs(check.latency_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DiagnosticsPage({ integrations, requestedIntegrationId }: DiagnosticsPageProps) {
  const integrationId =
    integrations.find((item) => item.id === requestedIntegrationId)?.id ?? integrations[0]?.id ?? null
  const integration = integrations.find((item) => item.id === integrationId) ?? null

  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [chosen, setChosen] = useState<{ integrationId: string; runId: string } | null>(null)

  const loadHealth = useCallback(
    () => (integrationId ? getIntegrationReliability(integrationId) : Promise.reject(new Error('No integration'))),
    [integrationId],
  )
  const loadRuns = useCallback(
    () => (integrationId ? listDiagnosticRuns(integrationId, 20) : Promise.resolve([])),
    [integrationId],
  )
  const health = useResource(integrationId ? loadHealth : null)
  const runs = useResource(integrationId ? loadRuns : null)

  const selectedRunId =
    (chosen && chosen.integrationId === integrationId ? chosen.runId : null) ?? runs.data?.[0]?.id ?? null
  const loadRun = useCallback(
    () => (selectedRunId ? getDiagnosticRun(selectedRunId) : Promise.reject(new Error('No run'))),
    [selectedRunId],
  )
  const run = useResource(selectedRunId ? loadRun : null)

  async function handleRun() {
    if (!integrationId) return
    setRunning(true)
    setRunError(null)
    try {
      const result = await runDiagnostics(integrationId)
      setChosen({ integrationId, runId: result.id })
      runs.reload()
      health.reload()
    } catch (err) {
      setRunError(errorMessage(err, 'Diagnostics failed to run.'))
    } finally {
      setRunning(false)
    }
  }

  if (integrations.length === 0) {
    return (
      <section className="panel">
        <h2>Diagnostics</h2>
        <p className="empty-state">Create an integration first.</p>
      </section>
    )
  }

  const current = health.data
  const displayedRun = run.data && run.data.id === selectedRunId ? run.data : null

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <h2>Guided diagnostics</h2>
        </div>
        <p className="muted">
          Runs a fixed, deterministic checklist on demand. GitHub diagnostics make one real{' '}
          <code>GET /user</code> call (logged as a real request). Stripe diagnostics only inspect stored
          webhook evidence. Diagnostics never change connection status, credentials, or events.
        </p>
        <div className="webhook-toolbar">
          <label>
            Integration
            <select
              value={integrationId ?? ''}
              onChange={(e) => navigate('diagnostics', { integration: e.target.value })}
              disabled={running}
            >
              {integrations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.provider})
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => void handleRun()} disabled={running || !integrationId}>
            {running ? 'Running diagnostics…' : 'Run diagnostics'}
          </button>
        </div>
        {runError ? (
          <p className="error-text" role="alert">
            {runError}
          </p>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Current health</h2>
          {current ? <HealthBadge state={current.health} /> : null}
        </div>
        <SectionStatus loading={health.loading} error={health.error} hasData={Boolean(current)} onRetry={health.reload} />
        {current && current.integration_id === integrationId ? (
          <>
            <p className="health-summary">{current.summary}</p>
            {current.evidence.length > 0 ? (
              <ul className="evidence-list">
                {current.evidence.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
            {current.recommended_action ? (
              <p className="recommendation">
                <strong>Next step:</strong> {current.recommended_action}
              </p>
            ) : null}
            <p className="muted small-text">
              {integration?.provider === 'github' ? `Connection: ${current.configuration}` : current.configuration}
            </p>
          </>
        ) : null}
      </section>

      <div className="diagnostics-layout">
        <section className="panel">
          <h2>Previous runs</h2>
          <SectionStatus loading={runs.loading} error={runs.error} hasData={Boolean(runs.data)} onRetry={runs.reload} />
          {runs.data && runs.data.length === 0 ? (
            <p className="empty-state">No diagnostic runs yet for this integration.</p>
          ) : null}
          <ul className="run-list">
            {(runs.data ?? []).map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === selectedRunId ? 'run-item run-item-active' : 'run-item'}
                  onClick={() => integrationId && setChosen({ integrationId, runId: item.id })}
                >
                  <span className="run-item-top">
                    <CheckBadge status={item.overall_status} />
                    <span className="small-text">{formatTime(item.started_at)}</span>
                  </span>
                  <span className="muted small-text">
                    {item.check_counts.passed} pass · {item.check_counts.warning} warn · {item.check_counts.failed}{' '}
                    fail · {item.check_counts.unknown} unknown
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Checks</h2>
          <SectionStatus
            loading={run.loading}
            error={run.error}
            hasData={Boolean(displayedRun)}
            onRetry={run.reload}
            loadingText="Loading run…"
          />
          {displayedRun ? (
            <>
              <div className="run-summary">
                <CheckBadge status={displayedRun.overall_status} />
                <span>{displayedRun.summary}</span>
              </div>
              <p className="muted small-text">
                Started {formatTime(displayedRun.started_at)} · completed {formatTime(displayedRun.completed_at)}
              </p>
              <ChecksTable run={displayedRun} />
            </>
          ) : !run.loading && !selectedRunId ? (
            <p className="empty-state">Run diagnostics to see check results.</p>
          ) : null}
        </section>
      </div>
    </>
  )
}

export default DiagnosticsPage
