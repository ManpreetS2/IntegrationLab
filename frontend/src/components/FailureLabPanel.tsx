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
import { errorMessage } from '../hooks'

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
        setError(errorMessage(err, 'Failed to load scenarios.'))
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
      setError(errorMessage(err, 'Simulation failed.'))
    } finally {
      setRunning(false)
    }
  }

  async function handleSelectRun(runId: string) {
    setError(null)
    try {
      setResult(await getFailureRun(runId))
    } catch (err) {
      setError(errorMessage(err, 'Failed to load run.'))
    }
  }

  const selectedScenario = scenarios.find((item) => item.id === scenario)

  if (githubIntegrations.length === 0) {
    return <p className="lg-empty">Create a GitHub integration to use Failure Lab.</p>
  }

  return (
    <div>
      <div className="lg-form-row">
        <label className="lg-field">
          Integration
          <select value={integrationId} onChange={(event) => setIntegrationId(event.target.value)} disabled={running}>
            {githubIntegrations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="lg-field">
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
        <button type="button" className="lg-case-button" onClick={() => void handleRun()} disabled={running || !scenario}>
          {running ? 'Running simulation…' : 'Run simulation'}
        </button>
      </div>
      {selectedScenario ? <p className="lg-note">{selectedScenario.description}</p> : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {result ? (
        <>
          <p className="lg-section-label">Observed · simulated</p>
          <dl className="lg-rules">
            <div>
              <dt>Scenario</dt>
              <dd>{result.scenario}</dd>
            </div>
            <div>
              <dt>Request</dt>
              <dd className="lg-mono">
                {result.request.method} {result.request.endpoint}
              </dd>
            </div>
            <div>
              <dt>HTTP status</dt>
              <dd>{result.observed.status_code ?? 'No response'}</dd>
            </div>
            <div>
              <dt>Latency</dt>
              <dd>{result.observed.latency_ms} ms · simulated</dd>
            </div>
            <div>
              <dt>Classification</dt>
              <dd>{result.observed.error_code ?? '—'}</dd>
            </div>
          </dl>
          <p className="lg-section-label">Diagnosis</p>
          <p className="lg-note">
            <strong>{result.diagnosis.title}</strong> · {result.diagnosis.summary} Retryable later:{' '}
            {result.diagnosis.retryable ? 'yes' : 'no'}.
          </p>
          <ul className="lg-links">
            {result.diagnosis.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {result.diagnosis.recommended_checks.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="lg-section-label">Recent simulations</p>
      {history.length === 0 ? <p className="lg-empty">No simulations yet.</p> : null}
      {history.length > 0 ? (
        <div className="lg-scroll-table">
          <table className="lg-table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Scenario</th>
                <th scope="col">Status</th>
                <th scope="col">Diagnosis</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row) => (
                <tr key={row.id} className={result?.id === row.id ? 'is-selected' : undefined}>
                  <td>
                    <button type="button" className="secondary-button" onClick={() => void handleSelectRun(row.id)}>
                      {new Date(row.created_at).toLocaleString()}
                    </button>
                  </td>
                  <td>{row.scenario}</td>
                  <td>{row.status_code ?? '—'}</td>
                  <td>{row.diagnosis_title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export default FailureLabPanel
