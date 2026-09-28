import { useState } from 'react'
import type { FormEvent } from 'react'
import type { IntegrationProvider } from '../types'

interface CreateIntegrationFormProps {
  onSubmit: (name: string, provider: IntegrationProvider) => Promise<void>
  disabled?: boolean
}

function CreateIntegrationForm({ onSubmit, disabled = false }: CreateIntegrationFormProps) {
  const [name, setName] = useState('')
  const [provider, setProvider] = useState<IntegrationProvider>('github')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const trimmedName = name.trim()
    if (!trimmedName) {
      setFormError('Display name is required.')
      return
    }

    setSubmitting(true)
    try {
      await onSubmit(trimmedName, provider)
      setName('')
      setProvider('github')
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Failed to create integration.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="create-form" onSubmit={handleSubmit}>
      <h2>Create integration</h2>
      <p className="muted">Adds a new record through POST /api/integrations.</p>

      <label htmlFor="integration-name">
        Display name
        <input
          id="integration-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme GitHub"
          disabled={disabled || submitting}
        />
      </label>

      <label htmlFor="integration-provider">
        Provider
        <select
          id="integration-provider"
          value={provider}
          onChange={(event) => setProvider(event.target.value as IntegrationProvider)}
          disabled={disabled || submitting}
        >
          <option value="github">GitHub</option>
          <option value="stripe">Stripe</option>
        </select>
      </label>

      {formError ? <p className="error-text">{formError}</p> : null}

      <button type="submit" disabled={disabled || submitting}>
        {submitting ? 'Creating…' : 'Create integration'}
      </button>
    </form>
  )
}

export default CreateIntegrationForm
