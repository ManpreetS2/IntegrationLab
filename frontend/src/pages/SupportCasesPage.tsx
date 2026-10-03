import { useCallback, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  addSupportCaseNote,
  createSupportCase,
  getSupportCase,
  getSupportCaseTimeline,
  listSupportCases,
  updateSupportCase,
} from '../api'
import SectionStatus from '../components/SectionStatus'
import { errorMessage, navigate, useHashRoute, useResource } from '../hooks'
import type { CaseSeverity, CaseStatus, Integration, SupportCaseDetail, TimelineItem } from '../types'

const SEVERITIES: CaseSeverity[] = ['SEV1', 'SEV2', 'SEV3', 'SEV4']
const NEXT_STATUS: Partial<Record<CaseStatus, CaseStatus[]>> = {
  investigating: ['identified', 'monitoring', 'resolved'],
  identified: ['monitoring', 'resolved', 'investigating'],
  monitoring: ['resolved', 'identified', 'investigating'],
  resolved: ['reopened'],
  reopened: ['identified', 'monitoring', 'resolved'],
}

interface SupportCasesPageProps {
  integrations: Integration[]
}

function shortCorr(id: string | null | undefined): string {
  if (!id) return '—'
  return `corr_${id.replace(/-/g, '').slice(0, 4)}…`
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    // Clipboard may be unavailable; ignore.
  }
}

function SupportCasesPage({ integrations }: SupportCasesPageProps) {
  const route = useHashRoute()
  const selectedId = route.params.get('case')
  const [openOnly, setOpenOnly] = useState(true)
  const [severity, setSeverity] = useState<CaseSeverity | ''>('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [note, setNote] = useState('')

  const loadCases = useCallback(
    () =>
      listSupportCases({
        open_only: openOnly ? true : undefined,
        severity: severity || undefined,
      }),
    [openOnly, severity],
  )
  const cases = useResource(loadCases)

  const loadDetail = useCallback(
    () => (selectedId ? getSupportCase(selectedId) : Promise.resolve(undefined)),
    [selectedId],
  )
  const detail = useResource(loadDetail)

  const loadTimeline = useCallback(
    () => (selectedId ? getSupportCaseTimeline(selectedId) : Promise.resolve([] as TimelineItem[])),
    [selectedId],
  )
  const timeline = useResource(loadTimeline)

  const integrationName = useMemo(() => {
    const map = new Map(integrations.map((item) => [item.id, item.name]))
    return (id: string) => map.get(id) ?? id.slice(0, 8)
  }, [integrations])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    const form = event.target as HTMLFormElement
    const data = new FormData(form)
    const integrationId = String(data.get('integration_id') || '')
    const title = String(data.get('title') || '').trim()
    if (!integrationId || !title) return
    setBusy(true)
    setMessage(null)
    try {
      const created = await createSupportCase({
        integration_id: integrationId,
        title,
        severity: (String(data.get('severity') || 'SEV3') as CaseSeverity) || 'SEV3',
        impact_summary: String(data.get('impact_summary') || '') || undefined,
        suspected_cause: String(data.get('suspected_cause') || '') || undefined,
      })
      form.reset()
      cases.reload()
      navigate('support', { case: created.id })
      setMessage(`Opened ${created.case_number}`)
    } catch (err) {
      setMessage(errorMessage(err, 'Unable to create support case.'))
    } finally {
      setBusy(false)
    }
  }

  async function changeStatus(next: CaseStatus) {
    if (!selectedId) return
    setBusy(true)
    setMessage(null)
    try {
      await updateSupportCase(selectedId, { status: next })
      detail.reload()
      timeline.reload()
      cases.reload()
    } catch (err) {
      setMessage(errorMessage(err, 'Unable to change status.'))
    } finally {
      setBusy(false)
    }
  }

  async function changeSeverity(next: CaseSeverity) {
    if (!selectedId) return
    setBusy(true)
    try {
      await updateSupportCase(selectedId, { severity: next })
      detail.reload()
      timeline.reload()
      cases.reload()
    } catch (err) {
      setMessage(errorMessage(err, 'Unable to change severity.'))
    } finally {
      setBusy(false)
    }
  }

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (!selectedId || !note.trim()) return
    setBusy(true)
    try {
      await addSupportCaseNote(selectedId, note.trim())
      setNote('')
      detail.reload()
      timeline.reload()
    } catch (err) {
      setMessage(errorMessage(err, 'Unable to add note.'))
    } finally {
      setBusy(false)
    }
  }

  const selected = detail.data as SupportCaseDetail | undefined

  return (
    <div className="support-layout">
      <section className="panel">
        <div className="panel-header">
          <h2>Support Cases</h2>
          <button type="button" className="secondary-button" onClick={cases.reload}>
            Refresh
          </button>
        </div>
        <div className="filter-row webhook-toolbar">
          <label>
            <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only
          </label>
          <label>
            Severity
            <select value={severity} onChange={(e) => setSeverity(e.target.value as CaseSeverity | '')}>
              <option value="">All</option>
              {SEVERITIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>
        <SectionStatus
          loading={cases.loading}
          error={cases.error}
          hasData={Boolean(cases.data)}
          onRetry={cases.reload}
          loadingText="Loading support cases…"
        />
        {cases.data ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Integration</th>
                  <th>Env</th>
                  <th>Opened</th>
                </tr>
              </thead>
              <tbody>
                {cases.data.map((item) => (
                  <tr key={item.id} className={item.id === selectedId ? 'row-active' : undefined}>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => navigate('support', { case: item.id })}
                      >
                        {item.case_number}
                      </button>
                      <div className="muted">{item.title}</div>
                    </td>
                    <td>
                      <span className={`status-chip status-chip-${item.severity.toLowerCase()}`}>{item.severity}</span>
                    </td>
                    <td>{item.status}</td>
                    <td>{integrationName(item.integration_id)}</td>
                    <td>{item.environment}</td>
                    <td>{new Date(item.opened_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <form className="stack-form" onSubmit={handleCreate}>
          <h3>Open support case</h3>
          <label>
            Integration
            <select name="integration_id" required defaultValue="">
              <option value="" disabled>
                Select integration
              </option>
              {integrations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.provider}) · {item.environment}
                </option>
              ))}
            </select>
          </label>
          <label>
            Title
            <input name="title" maxLength={200} required placeholder="Short investigation title" />
          </label>
          <label>
            Severity
            <select name="severity" defaultValue="SEV3">
              {SEVERITIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Impact summary
            <textarea name="impact_summary" maxLength={4000} rows={2} />
          </label>
          <label>
            Suspected cause
            <textarea name="suspected_cause" maxLength={4000} rows={2} placeholder="Observed facts only" />
          </label>
          <button type="submit" disabled={busy}>
            Create support case
          </button>
        </form>
        {message ? <p className="muted">{message}</p> : null}
      </section>

      {selectedId ? (
        <section className="panel">
          <SectionStatus
            loading={detail.loading}
            error={detail.error}
            hasData={Boolean(selected)}
            onRetry={detail.reload}
            loadingText="Loading case…"
          />
          {selected ? (
            <>
              <div className="panel-header">
                <div>
                  <h2>
                    {selected.case_number} · {selected.title}
                  </h2>
                  <p className="muted">
                    {selected.severity} · {selected.status} · {integrationName(selected.integration_id)} ·{' '}
                    {selected.environment}
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => selected.correlation_id && copyText(selected.correlation_id)}
                  title={selected.correlation_id ?? undefined}
                >
                  {shortCorr(selected.correlation_id)}
                </button>
              </div>

              <div className="summary-grid">
                <div>
                  <h3>Impact</h3>
                  <p>{selected.impact_summary || '—'}</p>
                </div>
                <div>
                  <h3>Suspected cause</h3>
                  <p>{selected.suspected_cause || '—'}</p>
                </div>
                <div>
                  <h3>Confirmed root cause</h3>
                  <p>{selected.confirmed_root_cause || '—'}</p>
                </div>
                <div>
                  <h3>Mitigation / resolution</h3>
                  <p>{selected.mitigation_summary || selected.resolution_summary || '—'}</p>
                </div>
              </div>

              <div className="filter-row webhook-toolbar">
                <label>
                  Severity
                  <select
                    value={selected.severity}
                    disabled={busy}
                    onChange={(e) => changeSeverity(e.target.value as CaseSeverity)}
                  >
                    {SEVERITIES.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="button-row">
                  {(NEXT_STATUS[selected.status] ?? []).map((next) => (
                    <button key={next} type="button" className="secondary-button" disabled={busy} onClick={() => changeStatus(next)}>
                      → {next}
                    </button>
                  ))}
                </div>
              </div>

              <h3>Pinned evidence</h3>
              {selected.evidence.length === 0 ? (
                <p className="muted">No evidence pinned yet.</p>
              ) : (
                <ul className="evidence-list">
                  {selected.evidence.map((item) => (
                    <li key={item.id}>
                      {item.is_simulated ? <strong>[SIMULATED] </strong> : null}
                      {item.safe_label}
                      <span className="muted"> · {item.evidence_type}</span>
                    </li>
                  ))}
                </ul>
              )}

              <h3>Timeline</h3>
              <SectionStatus
                loading={timeline.loading}
                error={timeline.error}
                hasData={Boolean(timeline.data)}
                onRetry={timeline.reload}
                loadingText="Loading timeline…"
              />
              <ol className="timeline-list">
                {(timeline.data ?? []).map((item, index) => (
                  <li key={`${item.timestamp}-${index}`}>
                    <div className="timeline-meta">
                      <strong>{item.title}</strong>
                      <span className="muted">{new Date(item.timestamp).toLocaleString()}</span>
                      {item.occurred_at && item.pinned_at ? (
                        <span className="muted" title="Evidence occurred vs when it was pinned">
                          occurred {new Date(item.occurred_at).toLocaleString()} · pinned{' '}
                          {new Date(item.pinned_at).toLocaleString()}
                        </span>
                      ) : null}
                      {item.correlation_short ? (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => item.correlation_id && copyText(item.correlation_id)}
                          title={item.correlation_id ?? undefined}
                        >
                          {item.correlation_short}
                        </button>
                      ) : null}
                      {item.is_simulated ? <span className="status-chip">simulated</span> : null}
                    </div>
                    <p>{item.summary}</p>
                  </li>
                ))}
              </ol>

              <form className="stack-form" onSubmit={submitNote}>
                <h3>Add note</h3>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={4000}
                  rows={3}
                  placeholder="Safe operational update (no secrets)"
                  required
                />
                <button type="submit" disabled={busy || !note.trim()}>
                  Add note
                </button>
              </form>
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}

export default SupportCasesPage
