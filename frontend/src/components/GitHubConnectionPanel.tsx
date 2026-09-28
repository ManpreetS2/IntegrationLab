import { useEffect, useState } from 'react'
import {
  checkGitHubConnection,
  getGitHubConnection,
  githubConnectUrl,
} from '../api'
import type { GitHubConnection, Integration } from '../types'

interface GitHubConnectionPanelProps {
  integration: Integration
  onStatusChange: () => Promise<void> | void
}

function GitHubConnectionPanel({ integration, onStatusChange }: GitHubConnectionPanelProps) {
  const [profile, setProfile] = useState<GitHubConnection | null>(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const showProfile = integration.status !== 'not_connected'

  useEffect(() => {
    if (!showProfile) {
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    void getGitHubConnection(integration.id)
      .then((data) => {
        if (!cancelled) setProfile(data)
      })
      .catch((err) => {
        if (!cancelled) {
          setProfile(null)
          setError(err instanceof Error ? err.message : 'Failed to load GitHub profile.')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [integration.id, showProfile])

  async function handleCheck() {
    setChecking(true)
    setMessage(null)
    setError(null)
    try {
      const result = await checkGitHubConnection(integration.id)
      if (result.ok) {
        setMessage(`Connection OK for @${result.login ?? 'unknown'}.`)
      } else {
        setError(result.error ?? 'Connection check failed.')
      }
      await onStatusChange()
      if (integration.status !== 'not_connected') {
        try {
          setProfile(await getGitHubConnection(integration.id))
        } catch {
          setProfile(null)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection check failed.')
    } finally {
      setChecking(false)
    }
  }

  if (integration.status === 'not_connected') {
    return (
      <div className="github-panel">
        <p className="muted">Not connected to GitHub yet.</p>
        <a className="button-link" href={githubConnectUrl(integration.id)}>
          Connect GitHub
        </a>
      </div>
    )
  }

  if (integration.status === 'needs_setup') {
    return (
      <div className="github-panel">
        <p className="error-text">Needs setup — GitHub authorization is missing or revoked.</p>
        <div className="github-actions">
          <a className="button-link" href={githubConnectUrl(integration.id)}>
            Reconnect GitHub
          </a>
          <button type="button" className="secondary-button" onClick={() => void handleCheck()} disabled={checking}>
            {checking ? 'Checking…' : 'Check connection'}
          </button>
        </div>
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    )
  }

  return (
    <div className="github-panel">
      {loading ? <p className="muted">Loading GitHub profile…</p> : null}
      {profile ? (
        <div className="github-profile">
          {profile.avatar_url ? (
            <img className="github-avatar" src={profile.avatar_url} alt="" width={40} height={40} />
          ) : null}
          <div>
            <p className="github-login">
              {profile.html_url ? (
                <a href={profile.html_url} target="_blank" rel="noreferrer">
                  @{profile.login}
                </a>
              ) : (
                <>@{profile.login}</>
              )}
            </p>
            <p className="muted">
              Connected · {profile.public_repos ?? 0} public repos
              {integration.last_checked_at
                ? ` · last checked ${new Date(integration.last_checked_at).toLocaleString()}`
                : null}
            </p>
          </div>
        </div>
      ) : null}
      <button type="button" onClick={() => void handleCheck()} disabled={checking}>
        {checking ? 'Checking…' : 'Check connection'}
      </button>
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </div>
  )
}

export default GitHubConnectionPanel
