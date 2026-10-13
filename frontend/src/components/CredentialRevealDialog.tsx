import { useEffect, useRef, useState } from 'react'
import type { IngestionCredentialCreated } from '../types'

interface CredentialRevealDialogProps {
  created: IngestionCredentialCreated | null
  onClose: () => void
}

function CredentialRevealDialog({ created, onClose }: CredentialRevealDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (created && !dialog.open) {
      setCopied(false)
      dialog.showModal()
    }
    if (!created && dialog.open) dialog.close()
  }, [created])

  function finish() {
    setCopied(false)
    const dialog = dialogRef.current
    if (dialog?.open) dialog.close()
    onClose()
  }

  async function copyValue() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.credential)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="secret-dialog"
      aria-labelledby="credential-reveal-title"
      onClose={finish}
    >
      {created ? (
        <div className="secret-dialog-body">
          <p className="eyebrow">Shown once</p>
          <h2 id="credential-reveal-title">Ingestion credential</h2>
          <p>
            Copy this value into the application process now. IntegrationLab will not show it again.
            It is not the operator key, and this page does not store it.
          </p>
          <label>
            Credential
            <input readOnly value={created.credential} spellCheck={false} autoComplete="off" />
          </label>
          <p className="muted small-text">
            Prefix <code>{created.key_prefix}</code>
            {created.label ? ` · ${created.label}` : ''}
          </p>
          <div className="button-row">
            <button type="button" onClick={() => void copyValue()}>
              {copied ? 'Copied' : 'Copy credential'}
            </button>
            <button type="button" className="secondary-button" onClick={finish}>
              I have copied it
            </button>
          </div>
        </div>
      ) : null}
    </dialog>
  )
}

export default CredentialRevealDialog
