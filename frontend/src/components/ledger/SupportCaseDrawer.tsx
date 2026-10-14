import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { addSupportCaseNote, createSupportCase } from '../../api'
import { errorMessage, pageHref } from '../../hooks'
import { supportCasePayload, type CaseDraft } from '../../ledger/case'
import type { CaseSeverity, SupportCaseDetail } from '../../types'

const SEVERITIES: CaseSeverity[] = ['SEV1', 'SEV2', 'SEV3', 'SEV4']

function SupportCaseDrawer({ draft, onClose }: { draft: CaseDraft; onClose: () => void }) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const [title, setTitle] = useState(draft.title)
  const [severity, setSeverity] = useState<CaseSeverity>(draft.severity)
  const [impact, setImpact] = useState(draft.impact)
  const [cause, setCause] = useState(draft.cause)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<SupportCaseDetail | null>(null)
  const [noteError, setNoteError] = useState<string | null>(null)

  useEffect(() => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const timer = window.setTimeout(() => document.getElementById('lg-case-title')?.focus(), 0)

    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
      const back = opener.current
      window.setTimeout(() => back?.focus(), 0)
    }
  }, [onClose])

  function trapTab(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Tab') return
    const root = dialogRef.current
    if (!root) return
    const items = Array.from(root.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href]')).filter(
      (element) => !element.hasAttribute('disabled') && element.getClientRects().length > 0,
    )
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setNoteError(null)
    try {
      const result = await createSupportCase(
        supportCasePayload(draft, { title, severity, impact, cause }),
      )
      if (note.trim()) {
        try {
          await addSupportCaseNote(result.id, note.trim())
        } catch (err) {
          setNoteError(errorMessage(err, 'The case was created, but the note was not saved.'))
        }
      }
      setCreated(result)
      window.setTimeout(() => document.getElementById('lg-case-link')?.focus(), 0)
    } catch (err) {
      setError(errorMessage(err, 'Unable to create support case.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <button type="button" className="lg-drawer-backdrop" aria-label="Close support case" onClick={onClose} />
      <div
        ref={dialogRef}
        className="lg-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={trapTab}
      >
        <h2 id={titleId}>Support case</h2>
        <p className="lg-note">{draft.pinNote}</p>
        {created ? (
          <div role="status">
            <p>
              Created <strong>{created.case_number}</strong>.
            </p>
            {noteError ? <p role="alert">{noteError}</p> : null}
            <p>
              <a id="lg-case-link" href={pageHref('support', { case: created.id })}>
                Open {created.case_number}
              </a>
            </p>
            <button type="button" className="secondary-button" onClick={onClose}>
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={onSubmit}>
            <label className="lg-field">
              Title
              <input
                id="lg-case-title"
                value={title}
                maxLength={200}
                required
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label className="lg-field">
              Severity
              <select value={severity} onChange={(event) => setSeverity(event.target.value as CaseSeverity)}>
                {SEVERITIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="lg-field">
              Impact
              <textarea value={impact} onChange={(event) => setImpact(event.target.value)} />
            </label>
            <label className="lg-field">
              Suspected cause
              <textarea value={cause} onChange={(event) => setCause(event.target.value)} />
            </label>
            <label className="lg-field">
              Note
              <textarea value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
            {error ? <p role="alert">{error}</p> : null}
            <div className="lg-drawer-actions">
              <button type="submit" className="lg-case-button" disabled={saving}>
                {saving ? 'Saving…' : 'Create support case'}
              </button>
              <button type="button" className="secondary-button" onClick={onClose}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </>
  )
}

export default SupportCaseDrawer
