import { useCallback, useState } from 'react'
import { getDiagnosticRun, getIntegrationReliability, listDiagnosticRuns, runDiagnostics } from '../api'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import LedgerList, { HealthWord } from '../components/ledger/LedgerList'
import SectionStatus from '../components/SectionStatus'
import { checkLabel, formatMs, formatProvider, formatTime } from '../format'
import { errorMessage, navigate, pageHref, useResource } from '../hooks'
import { shorten } from '../ledger/copy'
import type { DiagnosticCheck, DiagnosticRun, Integration } from '../types'

interface DiagnosticsPageProps {
  integrations: Integration[]
  requestedIntegrationId: string | null
}

function DiagnosticsPage({ integrations, requestedIntegrationId }: DiagnosticsPageProps) {
  const integrationId =
    integrations.find((item) => item.id === requestedIntegrationId)?.id ?? integrations[0]?.id ?? null
  const integration = integrations.find((item) => item.id === integrationId) ?? null
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [chosen, setChosen] = useState<{ integrationId: string; runId: string } | null>(null)
  const [pickedCheck, setPickedCheck] = useState<string | null>(null)

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
      setPickedCheck(null)
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
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker">Diagnostics</p>
          <h1 className="lg-finding">Create an integration first.</h1>
        </div>
        <EvidenceTrail title="Diagnostics" stations={[{ label: 'Scope', text: 'Checks run against one stored integration.' }]} />
      </div>
    )
  }

  const current = health.data && health.data.integration_id === integrationId ? health.data : null
  const displayedRun = run.data && run.data.id === selectedRunId ? run.data : null
  const instrumented = integration?.provider === 'instrumented_http'
  const checks = displayedRun?.checks ?? []
  const selectedCheck = checks.find((item) => item.check_code === pickedCheck) ?? checks[0] ?? null
  const finding = instrumented
    ? 'Diagnostics do not apply here.'
    : current
      ? shorten(current.summary, 88)
      : 'Run diagnostics.'

  return (
    <div className={running ? 'lg-busy' : undefined} aria-busy={running || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker">Diagnostics · on demand</p>
          <h1 className="lg-finding">{finding}</h1>
          <p className="lg-note">
            A fixed checklist. GitHub makes one real GET /user, logged as a real request. Stripe inspects stored webhook
            evidence. Checks never change connection status, credentials, or events.
          </p>
          <div className="lg-form-row">
            <label className="lg-field">
              Integration
              <select
                value={integrationId ?? ''}
                onChange={(event) => navigate('diagnostics', { integration: event.target.value })}
                disabled={running}
              >
                {integrations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {formatProvider(item.provider)}
                  </option>
                ))}
              </select>
            </label>
            {instrumented ? (
              <button type="button" disabled>
                Diagnostics unavailable
              </button>
            ) : (
              <button type="button" className="lg-case-button" onClick={() => void handleRun()} disabled={running || !integrationId}>
                {running ? 'Running diagnostics…' : 'Run diagnostics'}
              </button>
            )}
          </div>
          {instrumented ? (
            <p className="lg-note">
              Instrumented applications do not support guided diagnostics, GitHub OAuth, Stripe webhooks, or Failure Lab.
              Health comes from stored SDK observations on{' '}
              <a href={pageHref('telemetry', { integration: integration.id })}>Telemetry</a>.
            </p>
          ) : null}
          {runError ? (
            <p className="error-text" role="alert">
              {runError}
            </p>
          ) : null}
          <p className="lg-section-label">Current health</p>
          <SectionStatus loading={health.loading} error={health.error} hasData={Boolean(current)} onRetry={health.reload} />
          {current ? (
            <>
              <p className="lg-status">
                <HealthWord state={current.health} />
              </p>
              <p className="lg-note">{current.summary}</p>
              {current.recommended_action ? <p className="lg-note">Next step: {current.recommended_action}</p> : null}
            </>
          ) : null}
          {instrumented ? null : (
            <>
              <p className="lg-section-label">Previous runs</p>
              <SectionStatus loading={runs.loading} error={runs.error} hasData={Boolean(runs.data)} onRetry={runs.reload} />
              <LedgerList
                label="Diagnostic runs"
                columns={['When', 'Status', 'Passed', 'Failed']}
                rows={(runs.data ?? []).map((item) => ({
                  id: item.id,
                  title: checkLabel(item.overall_status),
                  meta: formatTime(item.started_at),
                  detail: `${item.check_counts.passed} pass · ${item.check_counts.failed} fail`,
                  cells: [
                    formatTime(item.started_at),
                    checkLabel(item.overall_status),
                    String(item.check_counts.passed),
                    String(item.check_counts.failed),
                  ],
                }))}
                selectedId={selectedRunId}
                onSelect={(id) => {
                  if (integrationId) setChosen({ integrationId, runId: id })
                  setPickedCheck(null)
                }}
                emptyText="No diagnostic runs yet for this integration."
              />
              <p className="lg-section-label">Checks</p>
              <SectionStatus
                loading={run.loading}
                error={run.error}
                hasData={Boolean(displayedRun)}
                onRetry={run.reload}
                loadingText="Loading run…"
              />
              {displayedRun ? <p className="lg-note">{displayedRun.summary}</p> : null}
              <LedgerList
                label="Checks"
                columns={['Status', 'Check', 'Evidence', 'Latency']}
                rows={checks.map((check) => ({
                  id: check.check_code,
                  title: check.title,
                  meta: checkLabel(check.status),
                  detail: shorten(check.evidence, 90),
                  cells: [
                    checkLabel(check.status),
                    <span key="title">
                      <strong>{check.title}</strong>
                      {check.required ? <span className="lg-muted"> · required</span> : null}
                    </span>,
                    shorten(check.evidence, 80),
                    formatMs(check.latency_ms),
                  ],
                }))}
                selectedId={selectedCheck?.check_code ?? null}
                onSelect={setPickedCheck}
                emptyText={selectedRunId ? 'This run has no checks.' : 'Run diagnostics to see check results.'}
              />
            </>
          )}
        </div>
        <EvidenceTrail
          title={selectedCheck?.title ?? integration?.name ?? 'Diagnostics'}
          stations={checkStations(selectedCheck, displayedRun)}
        />
      </div>
    </div>
  )
}

function checkStations(check: DiagnosticCheck | null, run: DiagnosticRun | null) {
  if (!check) {
    return [
      {
        label: 'Run',
        text: run?.summary ?? 'Select a run. Each check shows the evidence the diagnostic stored.',
      },
    ]
  }
  return [
    { label: 'Status', text: `${checkLabel(check.status)}${check.required ? ' · required' : ''}` },
    { label: 'Code', text: check.check_code },
    { label: 'Evidence', text: shorten(check.evidence, 180) },
    { label: 'Next', text: shorten(check.recommendation ?? 'No recommendation stored.', 160) },
    { label: 'Latency', text: formatMs(check.latency_ms) },
  ]
}

export default DiagnosticsPage
