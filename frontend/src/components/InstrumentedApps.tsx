import { useEffect, useState } from 'react'
import {
  createIngestionCredential,
  explainApiError,
  listIngestionCredentials,
  revokeIngestionCredential,
  rotateIngestionCredential,
} from '../api'
import { formatIntegrationStatus, formatTime } from '../format'
import type { IngestionCredentialCreated, IngestionCredentialView, Integration } from '../types'
import { recordsForSelection, type ScopedLoad } from '../viewSelection'
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
  const [credentialLoad, setCredentialLoad] = useState<ScopedLoad<IngestionCredentialView> | null>(null)
  const [loadError, setLoadError] = useState<{ ownerId: string; message: string } | null>(null)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState<IngestionCredentialCreated | null>(null)
  const [trackedId, setTrackedId] = useState(resolvedId)
  if (trackedId !== resolvedId) {
    setTrackedId(resolvedId)
    setRevealed(null)
    setLabel('')
  }
  const credentials = recordsForSelection(resolvedId, credentialLoad)
  const visibleCredentials = credentials ?? []

  useEffect(() => {
    if (!resolvedId) return
    const requestedId = resolvedId
    let cancelled = false
    listIngestionCredentials(requestedId).then(
      (items) => {
        if (cancelled) return
        setCredentialLoad({ ownerId: requestedId, records: items })
        setLoadError((current) => (current?.ownerId === requestedId ? null : current))
      },
      (err: unknown) => {
        if (cancelled) return
        setCredentialLoad({ ownerId: requestedId, records: [] })
        setLoadError({ ownerId: requestedId, message: explainApiError(err, 'Unable to load ingestion credentials.') })
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
    setLoadError(null)
    try {
      const created = await createIngestionCredential(selected.id, label.trim() || undefined)
      setLabel('')
      setRevealed(created)
      setCredentialLoad({ ownerId: selected.id, records: await listIngestionCredentials(selected.id) })
      setLoadError(null)
      onChanged()
    } catch (err) {
      setLoadError({ ownerId: selected.id, message: explainApiError(err, 'Unable to create an ingestion credential.') })
    } finally {
      setBusy(false)
    }
  }

  async function rotate(credential: IngestionCredentialView) {
    if (!selected || credential.integration_id !== selected.id) return
    const confirmed = window.confirm(
      'Rotate this credential? The current secret stops working immediately. The replacement is shown once.',
    )
    if (!confirmed) return
    setBusy(true)
    setLoadError(null)
    try {
      const created = await rotateIngestionCredential(selected.id, credential.id)
      setRevealed(created)
      setCredentialLoad({ ownerId: selected.id, records: await listIngestionCredentials(selected.id) })
      setLoadError(null)
      onChanged()
    } catch (err) {
      setLoadError({ ownerId: selected.id, message: explainApiError(err, 'Unable to rotate the credential.') })
    } finally {
      setBusy(false)
    }
  }

  async function revoke(credential: IngestionCredentialView) {
    if (!selected || credential.integration_id !== selected.id) return
    const confirmed = window.confirm(
      'Revoke this credential? Applications using it can no longer report observations. Revoking the last active credential returns the integration to Registered.',
    )
    if (!confirmed) return
    setBusy(true)
    setLoadError(null)
    try {
      await revokeIngestionCredential(selected.id, credential.id)
      setCredentialLoad({ ownerId: selected.id, records: await listIngestionCredentials(selected.id) })
      setLoadError(null)
      onChanged()
    } catch (err) {
      setLoadError({ ownerId: selected.id, message: explainApiError(err, 'Unable to revoke the credential.') })
    } finally {
      setBusy(false)
    }
  }

  if (!selected) {
    return (
      <p className="lg-empty">
        Register an application below with provider Instrumented HTTP. Registered means the record exists. It is not an
        OAuth connection.
      </p>
    )
  }

  const active = visibleCredentials.filter((item) => !item.revoked_at)
  const error = loadError?.ownerId === resolvedId ? loadError.message : null
  const loading = credentials === null

  return (
    <section>
      <p className="lg-section-label">Ingestion credentials</p>
      <p className="lg-note">
        {selected.name} reports its own HTTP outcomes. Registered and Instrumented are not OAuth Connected. Metadata
        only — the secret is returned once.
      </p>
      {integrations.length > 1 ? (
        <label className="lg-field">
          Application
          <select value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>
            {integrations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {formatIntegrationStatus(item.status)} · {item.environment}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <dl className="lg-rules">
        <div>
          <dt>Integration ID</dt>
          <dd className="lg-mono">{selected.id}</dd>
        </div>
        <div>
          <dt>Environment</dt>
          <dd>{selected.environment}</dd>
        </div>
      </dl>
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p className="lg-empty">Loading credentials…</p> : null}
      {credentials !== null && credentials.length === 0 && !error ? (
        <p className="lg-empty">No credentials yet. Generate one to move this application to Instrumented.</p>
      ) : null}
      {credentials !== null && credentials.length > 0 ? (
        <div className="lg-scroll-table">
          <table className="lg-table">
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
              {visibleCredentials.map((item) => (
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
        className="lg-form-row"
        onSubmit={(event) => {
          event.preventDefault()
          void createCredential()
        }}
      >
        <label className="lg-field">
          Label
          <input
            value={label}
            maxLength={64}
            placeholder="optional, for example laptop-dev"
            onChange={(event) => setLabel(event.target.value)}
            disabled={busy}
          />
        </label>
        <button type="submit" className="lg-case-button" disabled={busy || active.length >= 5}>
          {busy ? 'Working…' : 'Generate credential'}
        </button>
      </form>
      {active.length >= 5 ? (
        <p className="lg-note">Five active credentials is the limit. Rotate or revoke one first.</p>
      ) : null}

      <SdkSetup integrationId={selected.id} environment={selected.environment} />
      <CredentialRevealDialog
        created={revealed?.integration_id === selected.id ? revealed : null}
        onClose={closeReveal}
      />
    </section>
  )
}

export default InstrumentedApps
