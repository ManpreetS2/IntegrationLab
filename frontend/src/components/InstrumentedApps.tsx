import { useEffect, useState } from 'react'
import {
  createIngestionCredential,
  explainApiError,
  listIngestionCredentials,
  revokeIngestionCredential,
  rotateIngestionCredential,
} from '../api'
import { formatIntegrationStatus, formatTime } from '../format'
import { pageHref } from '../hooks'
import type { IngestionCredentialCreated, IngestionCredentialView, Integration } from '../types'
import CredentialRevealDialog from './CredentialRevealDialog'
import SdkSetup from './SdkSetup'

function InstrumentedApps({
  integrations,
  onChanged,
}: {
  integrations: Integration[]
  onChanged: () => void
}) {
  const [selectedId, setSelectedId] = useState(integrations[0]?.id ?? '')
  const resolvedId = integrations.some((item) => item.id === selectedId)
    ? selectedId
    : (integrations[0]?.id ?? '')
  const selected = integrations.find((item) => item.id === resolvedId) ?? null
  const [credentials, setCredentials] = useState<IngestionCredentialView[]>([])
  const [loading, setLoading] = useState(Boolean(integrations[0]?.id))
  const [error, setError] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState<IngestionCredentialCreated | null>(null)

  useEffect(() => {
    if (!resolvedId) return
    let cancelled = false
    listIngestionCredentials(resolvedId).then(
      (items) => {
        if (cancelled) return
        setCredentials(items)
        setError(null)
        setLoading(false)
      },
      (err: unknown) => {
        if (cancelled) return
        setCredentials([])
        setError(explainApiError(err, 'Unable to load ingestion credentials.'))
        setLoading(false)
      },
    )
    return () => {
      cancelled = true
    }
  }, [resolvedId])

  function closeReveal() {
    setRevealed(null)
  }

  async function createCredential() {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      const created = await createIngestionCredential(selected.id, label.trim() || undefined)
      setLabel('')
      setRevealed(created)
      setCredentials(await listIngestionCredentials(selected.id))
      onChanged()
    } catch (err) {
      setError(explainApiError(err, 'Unable to create an ingestion credential.'))
    } finally {
      setBusy(false)
    }
  }

  async function rotate(credential: IngestionCredentialView) {
    if (!selected) return
    const confirmed = window.confirm(
      'Rotate this credential? The current secret stops working immediately. The replacement is shown once.',
    )
    if (!confirmed) return
    setBusy(true)
    setError(null)
    try {
      const created = await rotateIngestionCredential(selected.id, credential.id)
      setRevealed(created)
      setCredentials(await listIngestionCredentials(selected.id))
      onChanged()
    } catch (err) {
      setError(explainApiError(err, 'Unable to rotate the credential.'))
    } finally {
      setBusy(false)
    }
  }

  async function revoke(credential: IngestionCredentialView) {
    if (!selected) return
    const confirmed = window.confirm(
      'Revoke this credential? Applications using it can no longer report observations. Revoking the last active credential returns the integration to Registered.',
    )
    if (!confirmed) return
    setBusy(true)
    setError(null)
    try {
      await revokeIngestionCredential(selected.id, credential.id)
      setCredentials(await listIngestionCredentials(selected.id))
      onChanged()
    } catch (err) {
      setError(explainApiError(err, 'Unable to revoke the credential.'))
    } finally {
      setBusy(false)
    }
  }

  if (!selected) {
    return (
      <section className="panel">
        <h2>Instrumented applications</h2>
        <p className="empty-state">
          Register an application below with provider Instrumented HTTP. Registered means the record
          exists. It is not an OAuth connection.
        </p>
      </section>
    )
  }

  const active = credentials.filter((item) => !item.revoked_at)

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>Instrumented applications</h2>
          <p className="muted small-text">
            These applications report their own HTTP outcomes. Registered and Instrumented are not
            OAuth Connected.
          </p>
        </div>
        <a className="button-link" href={pageHref('telemetry', { integration: selected.id })}>
          View SDK observations
        </a>
      </div>

      {integrations.length > 1 ? (
        <label>
          Application
          <select value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>
            {integrations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {formatIntegrationStatus(item.status)} · {item.environment}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p>
          <strong>{selected.name}</strong>{' '}
          <span className={`status-pill status-${selected.status}`}>
            {formatIntegrationStatus(selected.status)}
          </span>
        </p>
      )}

      <dl className="fact-grid">
        <div>
          <dt>Integration ID</dt>
          <dd className="mono-meta">{selected.id}</dd>
        </div>
        <div>
          <dt>Environment</dt>
          <dd>{selected.environment}</dd>
        </div>
      </dl>

      <h3>Ingestion credentials</h3>
      <p className="muted small-text">
        Metadata only. The secret is returned once when you create or rotate a credential.
      </p>
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p className="loading-text">Loading credentials…</p> : null}
      {!loading && credentials.length === 0 ? (
        <p className="empty-state">No credentials yet. Generate one to move this application to Instrumented.</p>
      ) : null}
      {credentials.length > 0 ? (
        <div className="table-wrap">
          <table className="integrations-table">
            <thead>
              <tr>
                <th>Label</th>
                <th>Prefix</th>
                <th>Created</th>
                <th>Last used</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {credentials.map((item) => (
                <tr key={item.id}>
                  <td>{item.label ?? '—'}</td>
                  <td>
                    <code>{item.key_prefix}</code>
                  </td>
                  <td className="nowrap">{formatTime(item.created_at)}</td>
                  <td className="nowrap">{formatTime(item.last_used_at)}</td>
                  <td>{item.revoked_at ? `Revoked ${formatTime(item.revoked_at)}` : 'Active'}</td>
                  <td>
                    {item.revoked_at ? (
                      '—'
                    ) : (
                      <div className="button-row">
                        <button
                          type="button"
                          className="secondary-button small-button"
                          disabled={busy}
                          onClick={() => void rotate(item)}
                        >
                          Rotate
                        </button>
                        <button
                          type="button"
                          className="secondary-button small-button"
                          disabled={busy}
                          onClick={() => void revoke(item)}
                        >
                          Revoke
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <form
        className="webhook-toolbar"
        onSubmit={(event) => {
          event.preventDefault()
          void createCredential()
        }}
      >
        <label>
          Label
          <input
            value={label}
            maxLength={64}
            placeholder="optional, for example laptop-dev"
            onChange={(event) => setLabel(event.target.value)}
            disabled={busy}
          />
        </label>
        <button type="submit" disabled={busy || active.length >= 5}>
          {busy ? 'Working…' : 'Generate credential'}
        </button>
      </form>
      {active.length >= 5 ? (
        <p className="muted small-text">Five active credentials is the limit. Rotate or revoke one first.</p>
      ) : null}

      <SdkSetup integrationId={selected.id} environment={selected.environment} />
      <CredentialRevealDialog created={revealed} onClose={closeReveal} />
    </section>
  )
}

export default InstrumentedApps
