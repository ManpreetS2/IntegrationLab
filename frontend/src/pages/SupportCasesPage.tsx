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
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import LedgerList from '../components/ledger/LedgerList'
import SectionStatus from '../components/SectionStatus'
import { formatTime } from '../format'
import { errorMessage, navigate, useHashRoute, useResource } from '../hooks'
import { shorten } from '../ledger/copy'
import type { CaseSeverity, CaseStatus, Integration, SupportCaseDetail, TimelineItem } from '../types'

const SEVERITIES: CaseSeverity[] = ['SEV1', 'SEV2', 'SEV3', 'SEV4']
const NEXT_STATUS: Partial<Record<CaseStatus, CaseStatus[]>> = {
  investigating: ['identified', 'monitoring', 'resolved'],
  identified: ['monitoring', 'resolved', 'investigating'],
  monitoring: ['resolved', 'identified', 'investigating'],
  resolved: ['reopened'],
  reopened: ['identified', 'monitoring', 'resolved'],
}

function shortCorr(id: string | null | undefined): string {
  if (!id) return '—'
  return `corr_${id.replace(/-/g, '').slice(0, 4)}…`
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    // Clipboard may be unavailable.
  }
}

function SupportCasesPage({ integrations }: { integrations: Integration[] }) {
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

  const rows = cases.data ?? []
  const selected = detail.data as SupportCaseDetail | undefined
  const openCount = rows.filter((item) => item.status !== 'resolved').length
  const finding = selected
    ? selected.title
    : !cases.data
      ? 'Support cases'
      : rows.length === 0
        ? openOnly
          ? 'No open cases.'
          : 'No cases yet.'
        : openCount === 1
          ? 'One case is open.'
          : `${openCount} cases are open.`

  const evidenceStations =
    selected && selected.evidence.length > 0
      ? selected.evidence.slice(0, 5).map((item) => ({
          label: item.evidence_type,
          text: `${item.is_simulated && !item.safe_label.includes('[SIMULATED]') ? '[SIMULATED] ' : ''}${shorten(item.safe_label, 160)}`,
        }))
      : [{ label: 'Evidence', text: selected ? 'No evidence pinned yet.' : 'Select a case to see pinned references.' }]

  return (
    <div className={busy || cases.loading ? 'lg-busy' : undefined} aria-busy={busy || cases.loading || undefined}>
      <div className="lg-page">
        <div className="lg-main">
          <p className="lg-kicker">
            Support cases
            {cases.loading && cases.data ? <span className="lg-refresh">Refreshing…</span> : null}
          </p>
          <h1 className="lg-finding">{finding}</h1>
          <div className="lg-toolbar">
            <label className="lg-inline-check">
              <input type="checkbox" checked={openOnly} onChange={(event) => setOpenOnly(event.target.checked)} />
              Open only
            </label>
            <label className="lg-field">
              Severity
              <select value={severity} onChange={(event) => setSeverity(event.target.value as CaseSeverity | '')}>
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
            <LedgerList
              label="Support cases"
              columns={['Case', 'Severity', 'Status', 'Integration']}
              rows={rows.map((item) => ({
                id: item.id,
                title: item.case_number,
                meta: item.severity,
                detail: shorten(item.title, 80),
                cells: [
                  <span key="case">
                    <strong>{item.case_number}</strong>
                    <span className="lg-muted"> · {shorten(item.title, 48)}</span>
                  </span>,
                  item.severity,
                  item.status,
                  integrationName(item.integration_id),
                ],
              }))}
              selectedId={selectedId}
              onSelect={(id) => navigate('support', { case: id })}
              emptyText={openOnly ? 'No open cases.' : 'No cases yet.'}
            />
          ) : null}
          {selectedId ? (
            <>
              <SectionStatus
                loading={detail.loading}
                error={detail.error}
                hasData={Boolean(selected)}
                onRetry={detail.reload}
                loadingText="Loading case…"
              />
              {selected ? (
                <>
                  <p className="lg-status">
                    <span>
                      {selected.case_number} · {selected.severity} · {selected.status}
                    </span>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => selected.correlation_id && copyText(selected.correlation_id)}
                      title={selected.correlation_id ?? undefined}
                    >
                      {shortCorr(selected.correlation_id)}
                    </button>
                  </p>
                  <p className="lg-note">
                    {integrationName(selected.integration_id)} · {selected.environment} · opened{' '}
                    {formatTime(selected.opened_at)}
                  </p>
                  <dl className="lg-rules">
                    <div>
                      <dt>Impact</dt>
                      <dd>{selected.impact_summary || '—'}</dd>
                    </div>
                    <div>
                      <dt>Suspected cause</dt>
                      <dd>{selected.suspected_cause || '—'}</dd>
                    </div>
                    <div>
                      <dt>Confirmed cause</dt>
                      <dd>{selected.confirmed_root_cause || '—'}</dd>
                    </div>
                    <div>
                      <dt>Resolution</dt>
                      <dd>{selected.mitigation_summary || selected.resolution_summary || '—'}</dd>
                    </div>
                  </dl>
                  <div className="lg-form-row">
                    <label className="lg-field">
                      Severity
                      <select
                        value={selected.severity}
                        disabled={busy}
                        onChange={(event) => changeSeverity(event.target.value as CaseSeverity)}
                      >
                        {SEVERITIES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    {(NEXT_STATUS[selected.status] ?? []).map((next) => (
                      <button key={next} type="button" className="secondary-button" disabled={busy} onClick={() => changeStatus(next)}>
                        {next}
                      </button>
                    ))}
                  </div>
                  <p className="lg-section-label">Timeline</p>
                  <SectionStatus
                    loading={timeline.loading}
                    error={timeline.error}
                    hasData={Boolean(timeline.data)}
                    onRetry={timeline.reload}
                    loadingText="Loading timeline…"
                  />
                  <ul className="lg-links">
                    {(timeline.data ?? []).map((item, index) => (
                      <li key={`${item.timestamp}-${index}`}>
                        <strong>{item.title}</strong>
                        <span className="lg-muted"> · {formatTime(item.timestamp)}</span>
                        {item.is_simulated ? <span className="lg-muted"> · simulated</span> : null}
                        <div>{item.summary}</div>
                      </li>
                    ))}
                  </ul>
                  <form className="lg-form" onSubmit={submitNote}>
                    <label className="lg-field">
                      Note
                      <textarea
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        maxLength={4000}
                        rows={3}
                        placeholder="Safe operational update. No secrets."
                        required
                      />
                    </label>
                    <button type="submit" className="lg-case-button" disabled={busy || !note.trim()}>
                      Add note
                    </button>
                  </form>
                </>
              ) : null}
            </>
          ) : null}
          <section>
            <p className="lg-section-label">Open a case</p>
            <form className="lg-form" onSubmit={handleCreate}>
              <label className="lg-field">
                Integration
                <select name="integration_id" required defaultValue="">
                  <option value="" disabled>
                    Select integration
                  </option>
                  {integrations.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {item.provider} · {item.environment}
                    </option>
                  ))}
                </select>
              </label>
              <label className="lg-field">
                Title
                <input name="title" maxLength={200} required placeholder="Short investigation title" />
              </label>
              <label className="lg-field">
                Severity
                <select name="severity" defaultValue="SEV3">
                  {SEVERITIES.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="lg-field">
                Impact summary
                <textarea name="impact_summary" maxLength={4000} rows={2} />
              </label>
              <label className="lg-field">
                Suspected cause
                <textarea name="suspected_cause" maxLength={4000} rows={2} placeholder="Observed facts only" />
              </label>
              <button type="submit" className="lg-case-button" disabled={busy}>
                Create support case
              </button>
            </form>
            {message ? <p className="lg-note">{message}</p> : null}
          </section>
        </div>
        <EvidenceTrail title={selected?.case_number ?? 'Evidence'} stations={evidenceStations} />
      </div>
    </div>
  )
}

export default SupportCasesPage
