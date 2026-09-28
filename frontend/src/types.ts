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

export type WebhookProcessingStatus =
  | 'pending'
  | 'processing'
  | 'processed'
  | 'retry_scheduled'
  | 'failed'
  | 'ignored'
  | 'dismissed'

export interface WebhookEventSummary {
  id: string
  integration_id: string
  provider: string
  provider_event_id: string
  event_type: string
  provider_object_id: string | null
  livemode: boolean | null
  amount: number | null
  currency: string | null
  processing_status: WebhookProcessingStatus
  delivery_count: number
  attempt_count: number
  cycle_attempt_count: number
  retry_cycle: number
  manual_retry_count: number
  max_attempts: number
  next_attempt_at: string | null
  first_received_at: string
  last_received_at: string
  processed_at: string | null
  failed_at: string | null
  dismissed_at: string | null
  last_error_code: string | null
  last_error_message: string | null
}

export interface WebhookEffect {
  id: string
  effect_key: string
  effect_type: string
  provider_object_id: string | null
  summary: string | null
  applied_at: string
}

export interface WebhookAttempt {
  id: string
  attempt_number: number
  retry_cycle: number
  cycle_attempt_number: number
  started_at: string
  finished_at: string | null
  outcome: 'in_progress' | 'succeeded' | 'ignored' | 'failed' | 'abandoned'
  error_code: string | null
  error_message: string | null
  retryable: boolean | null
  scheduled_delay_seconds: number | null
  manual: boolean
}

export interface WebhookEventDetail extends WebhookEventSummary {
  api_version: string | null
  provider_created_at: string | null
  processing_started_at: string | null
  signature_verified: boolean
  effects: WebhookEffect[]
  attempts: WebhookAttempt[]
}

export interface WebhookSummary {
  received: number
  duplicate_deliveries: number
  pending: number
  processing: number
  processed: number
  retry_scheduled: number
  failed: number
  ignored: number
  dismissed: number
}

export interface ProcessDueResult {
  processed: number
  retry_scheduled: number
  failed: number
  ignored: number
  skipped: number
}
