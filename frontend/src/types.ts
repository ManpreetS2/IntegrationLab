/** Shared TypeScript types for IntegrationLab API responses. */

export type IntegrationStatus = 'not_connected' | 'connected' | 'needs_setup'

export type IntegrationProvider = 'github' | 'stripe'

export interface Integration {
  id: string
  name: string
  provider: IntegrationProvider
  status: IntegrationStatus
  created_at: string
  last_checked_at: string | null
}

export interface IntegrationCreateRequest {
  name: string
  provider: IntegrationProvider
}

export interface HealthResponse {
  status: string
}
