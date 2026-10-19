import { useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage } from '../hooks'
import type { Environment, IntegrationProvider } from '../types'

interface CreateIntegrationFormProps {
  onSubmit: (name: string, provider: IntegrationProvider, environment?: Environment) => Promise<void>
  disabled?: boolean
}

function CreateIntegrationForm({ onSubmit, disabled = false }: CreateIntegrationFormProps) {
  const [name, setName] = useState('')
  const [provider, setProvider] = useState<IntegrationProvider>('github')
  const [environment, setEnvironment] = useState<Environment>('local')
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
      await onSubmit(trimmedName, provider, provider === 'instrumented_http' ? environment : undefined)
      setName('')
      setProvider('github')
    } catch (error) {
      setFormError(errorMessage(error, 'Failed to create integration.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="lg-form" onSubmit={handleSubmit}>
      <p className="lg-note">The record is created through the integrations API. A secret is never part of this form.</p>

      <label className="lg-field" htmlFor="integration-name">
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

      <label className="lg-field" htmlFor="integration-provider">
        Provider
        <select
          id="integration-provider"
          value={provider}
          onChange={(event) => setProvider(event.target.value as IntegrationProvider)}
          disabled={disabled || submitting}
        >
          <option value="github">GitHub</option>
          <option value="stripe">Stripe</option>
          <option value="instrumented_http">Instrumented HTTP</option>
        </select>
      </label>

      {provider === 'instrumented_http' ? (
        <label className="lg-field" htmlFor="integration-environment">
          Environment
          <select
            id="integration-environment"
            value={environment}
            onChange={(event) => setEnvironment(event.target.value as Environment)}
            disabled={disabled || submitting}
          >
            <option value="local">local</option>
            <option value="test">test</option>
            <option value="staging">staging</option>
            <option value="production">production</option>
          </select>
        </label>
      ) : null}

      {formError ? <p className="error-text">{formError}</p> : null}

      <button type="submit" className="lg-case-button" disabled={disabled || submitting}>
        {submitting ? 'Creating…' : 'Create integration'}
      </button>
    </form>
  )
}

export default CreateIntegrationForm
