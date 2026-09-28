/** Shared TypeScript types for IntegrationLab API responses. */

export type IntegrationStatus = 'not_connected' | 'connected' | 'needs_setup'

export type IntegrationProvider = 'github' | 'stripe'

export type FailureScenarioId =
  | 'unauthorized_401'
  | 'forbidden_403'
  | 'not_found_404'
  | 'rate_limited_429'
  | 'provider_500'
  | 'timeout'
  | 'malformed_json'
  | 'transport_error'

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

export interface GitHubConnection {
  integration_id: string
  connected: boolean
  login: string | null
  avatar_url: string | null
  html_url: string | null
  public_repos: number | null
  granted_scopes: string[]
  connected_at: string | null
  last_synced_at: string | null
  status: string | null
}

export interface GitHubCheckResult {
  ok: boolean
  status: string
  login: string | null
  public_repos: number | null
  last_checked_at: string | null
  error: string | null
}

export interface ProviderRequestLog {
  id: string
  integration_id: string | null
  provider: string
  method: string
  endpoint: string
  status_code: number | null
  latency_ms: number
  timestamp: string
  error_message: string | null
  rate_limit_remaining: number | null
  is_simulated: boolean
  scenario: string | null
}

export interface FailureScenarioInfo {
  id: FailureScenarioId
  label: string
  description: string
}

export interface FailureLabRun {
  id: string
  integration_id: string
  provider: string
  scenario: FailureScenarioId
  request: {
    method: string
    endpoint: string
  }
  observed: {
    status_code: number | null
    latency_ms: number
    error_code: string | null
    rate_limit_remaining: number | null
  }
  diagnosis: {
    code: string
    title: string
    summary: string
    retryable: boolean
    evidence: string[]
    recommended_checks: string[]
  }
  created_at: string
}

export interface FailureLabRunListItem {
  id: string
  integration_id: string
  provider: string
  scenario: FailureScenarioId
  status_code: number | null
  latency_ms: number
  error_code: string | null
  diagnosis_code: string
  diagnosis_title: string
  retryable: boolean
  created_at: string
}
