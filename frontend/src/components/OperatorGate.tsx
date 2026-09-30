import { useCallback, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  ApiError,
  getOperatorAuthStatus,
  verifyOperatorAccess,
} from '../api'
import {
  clearOperatorApiKey,
  getOperatorApiKey,
  setOperatorApiKey,
} from '../auth'

interface OperatorGateProps {
  children: ReactNode
}

type GateState = 'checking' | 'locked' | 'unlocked' | 'unavailable'

function OperatorGate({ children }: OperatorGateProps) {
  const [state, setState] = useState<GateState>('checking')
  const [keyInput, setKeyInput] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  const bootstrap = useCallback(async () => {
    setState('checking')
    setMessage(null)
    try {
      const status = await getOperatorAuthStatus()
      if (!status.required) {
        setState('unlocked')
        return
      }

      const existing = getOperatorApiKey()
      if (!existing) {
        setState('locked')
        return
      }

      try {
        await verifyOperatorAccess()
        setState('unlocked')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearOperatorApiKey()
          setState('locked')
          setMessage('The saved operator key is no longer valid.')
          return
        }
        throw error
      }
    } catch {
      setState('unavailable')
      setMessage('The API is unavailable, so operator access could not be checked.')
    }
  }, [])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const candidate = keyInput.trim()
    if (!candidate) {
      setMessage('Enter the operator key.')
      return
    }

    setMessage(null)
    setOperatorApiKey(candidate)
    try {
      await verifyOperatorAccess()
      setKeyInput('')
      setState('unlocked')
    } catch (error) {
      clearOperatorApiKey()
      if (error instanceof ApiError && error.status === 401) {
        setMessage('Invalid operator key.')
      } else {
        setMessage('The API could not verify the operator key.')
      }
      setState('locked')
    }
  }

  if (state === 'unlocked') return <>{children}</>

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-live="polite">
        <p className="eyebrow">IntegrationLab</p>
        <h1>Operator console</h1>

        {state === 'checking' ? (
          <p className="muted">Checking operator access…</p>
        ) : null}

        {state === 'unavailable' ? (
          <>
            <p className="error-text">{message}</p>
            <button type="button" onClick={() => void bootstrap()}>
              Retry
            </button>
          </>
        ) : null}

        {state === 'locked' ? (
          <>
            <p className="muted">
              This deployment protects operator API routes with a bearer key. The key stays in this
              tab&apos;s session storage and is never compiled into the frontend bundle.
            </p>
            <form className="auth-form" onSubmit={handleSubmit}>
              <label>
                Operator key
                <input
                  type="password"
                  value={keyInput}
                  onChange={(event) => setKeyInput(event.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  autoFocus
                />
              </label>
              {message ? <p className="error-text">{message}</p> : null}
              <button type="submit">Unlock console</button>
            </form>
          </>
        ) : null}
      </section>
    </main>
  )
}

export default OperatorGate
