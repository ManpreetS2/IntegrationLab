import { useEffect, useMemo, useState } from 'react'
import {
  getFailureRun,
  listFailureRuns,
  listFailureScenarios,
  runFailureScenario,
} from '../api'
import type {
  FailureLabRun,
  FailureLabRunListItem,
  FailureScenarioId,
  FailureScenarioInfo,
  Integration,
} from '../types'

interface FailureLabPanelProps {
  integrations: Integration[]
  onCompleted: () => Promise<void> | void
}

function FailureLabPanel({ integrations, onCompleted }: FailureLabPanelProps) {
  const githubIntegrations = useMemo(
    () => integrations.filter((item) => item.provider === 'github'),
    [integrations],
  )

  const [scenarios, setScenarios] = useState<FailureScenarioInfo[]>([])
  const [integrationId, setIntegrationId] = useState('')
  const [scenario, setScenario] = useState<FailureScenarioId | ''>('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<FailureLabRun | null>(null)
  const [history, setHistory] = useState<FailureLabRunListItem[]>([])

  useEffect(() => {
    void listFailureScenarios()
      .then((items) => {
        setScenarios(items)
        if (items[0]) setScenario(items[0].id)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load scenarios.')
      })
  }, [])

  useEffect(() => {
    if (githubIntegrations.length === 0) {
      setIntegrationId('')
      return
    }
    if (!githubIntegrations.some((item) => item.id === integrationId)) {
      setIntegrationId(githubIntegrations[0].id)
    }
  }, [githubIntegrations, integrationId])

  async function refreshHistory() {
    const rows = await listFailureRuns({ limit: 25 })
    setHistory(rows)
  }

  useEffect(() => {
    void refreshHistory().catch(() => {
      /* history is secondary; main error surface is the run action */
    })
  }, [])

  async function handleRun() {
    if (!integrationId || !scenario) return
    setRunning(true)
    setError(null)
    try {
      const run = await runFailureScenario({
        integration_id: integrationId,
        scenario,
      })
      setResult(run)
      await refreshHistory()
      await onCompleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed.')
    } finally {
      setRunning(false)
    }
  }

  async function handleSelectRun(runId: string) {
    setError(null)
    try {
      setResult(await getFailureRun(runId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run.')
    }
  }

  const selectedScenario = scenarios.find((item) => item.id === scenario)

  if (githubIntegrations.length === 0) {
    return (
      <div className="failure-lab">
        <p className="muted">Create a GitHub integration to use Failure Lab.</p>
      </div>
    )
  }

  return (
    <div className="failure-lab">
      <p className="muted">
        Reproduce common provider integration failures in a controlled environment without damaging
        the real connection.
      </p>

      <div className="failure-lab-controls">
        <label>
          Integration
          <select
            value={integrationId}
            onChange={(event) => setIntegrationId(event.target.value)}
            disabled={running}
          >
            {githubIntegrations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Scenario
          <select
            value={scenario}
            onChange={(event) => setScenario(event.target.value as FailureScenarioId)}
            disabled={running}
          >
            {scenarios.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <button type="button" onClick={() => void handleRun()} disabled={running || !scenario}>
          {running ? 'Running simulation…' : 'Run Simulation'}
        </button>
      </div>

      {selectedScenario ? <p className="muted scenario-hint">{selectedScenario.description}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      {result ? (
        <div className="failure-result">
          <div className="failure-observed">
            <h3>Observed</h3>
            <dl className="result-grid">
              <div>
                <dt>Scenario</dt>
                <dd>{result.scenario}</dd>
              </div>
              <div>
                <dt>Request</dt>
                <dd>
                  {result.request.method} {result.request.endpoint}
                </dd>
              </div>
              <div>
                <dt>HTTP status</dt>
                <dd>{result.observed.status_code ?? 'null (no response)'}</dd>
              </div>
              <div>
                <dt>Latency</dt>
                <dd>{result.observed.latency_ms}ms (simulated)</dd>
              </div>
              <div>
                <dt>Error classification</dt>
                <dd>{result.observed.error_code ?? '—'}</dd>
              </div>
              <div>
                <dt>Rate limit remaining</dt>
                <dd>{result.observed.rate_limit_remaining ?? '—'}</dd>
              </div>
            </dl>
          </div>

          <div className="failure-diagnosis">
            <h3>Diagnosis</h3>
            <p className="diagnosis-title">{result.diagnosis.title}</p>
            <p>{result.diagnosis.summary}</p>
            <p>
              <strong>Retryable later:</strong> {result.diagnosis.retryable ? 'Yes' : 'No'}
            </p>
            <div>
              <h4>Evidence</h4>
              <ul>
                {result.diagnosis.evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4>Recommended checks</h4>
              <ul>
                {result.diagnosis.recommended_checks.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : null}

      <div className="failure-history">
        <h3>Recent Failure Lab runs</h3>
        {history.length === 0 ? (
          <p className="empty-state">No simulations yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="integrations-table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Scenario</th>
                  <th scope="col">Status</th>
                  <th scope="col">Diagnosis</th>
                  <th scope="col">Retryable</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <button
                        type="button"
                        className="linkish-button"
                        onClick={() => void handleSelectRun(row.id)}
                      >
                        {new Date(row.created_at).toLocaleString()}
                      </button>
                    </td>
                    <td>{row.scenario}</td>
                    <td>{row.status_code ?? '—'}</td>
                    <td>{row.diagnosis_title}</td>
                    <td>{row.retryable ? 'Yes' : 'No'}</td>
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

export default FailureLabPanel
