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

export type Environment = 'local' | 'test' | 'staging' | 'production'
export type CaseSeverity = 'SEV1' | 'SEV2' | 'SEV3' | 'SEV4'
export type CaseStatus = 'investigating' | 'identified' | 'monitoring' | 'resolved' | 'reopened'
export type EvidenceType =
  | 'provider_request'
  | 'webhook_event'
  | 'webhook_attempt'
  | 'diagnostic_run'
  | 'failure_lab_run'
  | 'audit_event'

export interface Integration {
  id: string
  name: string
  provider: IntegrationProvider
  status: IntegrationStatus
  environment: Environment
  owner_team: string | null
  criticality: string | null
  support_tier: string | null
  runbook_url: string | null
  escalation_contact: string | null
  go_live_date: string | null
  expected_traffic: string | null
  last_verified_at: string | null
  created_at: string
  last_checked_at: string | null
}

export interface IntegrationCreateRequest {
  name: string
  provider: IntegrationProvider
  environment?: Environment
}

export interface SupportCase {
  id: string
  case_number: string
  integration_id: string
  environment: Environment
  title: string
  severity: CaseSeverity
  status: CaseStatus
  owner: string | null
  impact_summary: string | null
  suspected_cause: string | null
  confirmed_root_cause: string | null
  mitigation_summary: string | null
  resolution_summary: string | null
  correlation_id: string | null
  opened_at: string
  acknowledged_at: string | null
  identified_at: string | null
  monitoring_at: string | null
  resolved_at: string | null
  reopened_at: string | null
  created_at: string
  updated_at: string
}

export interface SupportCaseNote {
  id: string
  support_case_id: string
  body: string
  correlation_id: string | null
  created_at: string
}

export interface SupportCaseEvidence {
  id: string
  support_case_id: string
  evidence_type: EvidenceType
  evidence_id: string
  safe_label: string
  is_simulated: boolean
  correlation_id: string | null
  pinned_at: string
}

export interface SupportCaseDetail extends SupportCase {
  notes: SupportCaseNote[]
  evidence: SupportCaseEvidence[]
}

export interface TimelineItem {
  timestamp: string
  type: string
  title: string
  summary: string
  source_type: string | null
  source_id: string | null
  correlation_id: string | null
  correlation_short: string | null
  is_simulated: boolean
  occurred_at?: string | null
  pinned_at?: string | null
}

export interface OperatorAuditEvent {
  id: string
  action: string
  target_type: string
  target_id: string | null
  integration_id: string | null
  support_case_id: string | null
  correlation_id: string | null
  actor_type: string
  outcome: string
  safe_summary: string
  metadata: Record<string, unknown> | null
  created_at: string
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

// ------------------------------------------------------------ reliability

export type HealthState = 'healthy' | 'degraded' | 'failed' | 'unknown' | 'not_configured'

export type LatencyBand = 'normal' | 'elevated' | 'slow'

export type FailureSource = 'provider_request' | 'webhook_processing' | 'failure_lab' | 'diagnostic'

export type Severity = 'info' | 'warning' | 'error' | 'critical'

export interface RequestMetrics {
  request_count: number
  success_count: number
  failure_count: number
  error_rate: number | null
  average_latency_ms: number | null
  p95_latency_ms: number | null
  latest_latency_ms: number | null
  latest_latency_band: LatencyBand | null
  latest_status_code: number | null
  latest_error_code: string | null
  latest_endpoint: string | null
  latest_request_at: string | null
  rate_limit_remaining: number | null
}

export interface WebhookMetrics {
  verification_configured: boolean
  events_total: number
  events_in_window: number
  duplicate_deliveries: number
  pending: number
  stale_pending: number
  processing: number
  stale_processing: number
  retry_scheduled: number
  failed: number
  processed: number
  ignored: number
  dismissed: number
  failed_attempts_in_window: number
  successful_attempts_in_window: number
  retries_scheduled_in_window: number
  last_received_at: string | null
}

export interface DiagnosticRunBrief {
  id: string
  overall_status: DiagnosticRunStatus
  summary: string | null
  started_at: string
  completed_at: string | null
}

export interface IntegrationHealth {
  integration_id: string
  name: string
  provider: IntegrationProvider
  connection_status: IntegrationStatus
  configuration: string
  health: HealthState
  summary: string
  evidence: string[]
  recommended_action: string | null
  last_activity_at: string | null
  last_checked_at: string | null
  request_metrics: RequestMetrics | null
  webhook_metrics: WebhookMetrics | null
  latest_diagnostic: DiagnosticRunBrief | null
}

export interface SystemHealth {
  database: HealthState
  checked_at: string
}

export type HealthTotals = Record<HealthState, number>

export interface OperationalMetrics {
  real_provider_requests: number
  real_provider_errors: number
  simulated_requests: number
  failure_lab_runs: number
  webhook_events_received: number
  duplicate_webhook_deliveries: number
  webhook_processed: number
  webhook_retry_scheduled: number
  webhook_failed: number
  webhook_pending: number
  diagnostic_runs: number
}

export interface FailureItem {
  id: string
  source: FailureSource
  integration_id: string | null
  integration_name: string | null
  provider: string
  occurred_at: string
  severity: Severity
  code: string
  summary: string
  simulated: boolean
  method: string | null
  endpoint: string | null
  status_code: number | null
  latency_ms: number | null
  webhook_event_id: string | null
  event_type: string | null
  attempt_count: number | null
  diagnosis_title: string | null
  retryable: boolean | null
  diagnostic_run_id: string | null
}

export interface ReliabilityOverview {
  generated_at: string
  window_hours: number
  system: SystemHealth
  totals: HealthTotals
  integrations: IntegrationHealth[]
  recent_failures: FailureItem[]
  operational: OperationalMetrics
}

export interface IntegrationReliabilityDetail extends IntegrationHealth {
  generated_at: string
  window_hours: number
  recent_requests: ProviderRequestLog[]
  recent_webhook_events: WebhookEventSummary[]
  recent_failures: FailureItem[]
}

export interface RequestMetricsResponse {
  window_hours: number
  provider: string | null
  integration_id: string | null
  is_simulated: boolean | null
  metrics: RequestMetrics
}

// ------------------------------------------------------------ diagnostics

export type CheckStatus = 'pass' | 'warning' | 'fail' | 'unknown'

export type DiagnosticRunStatus = CheckStatus | 'running'

export interface DiagnosticCheck {
  position: number
  check_code: string
  title: string
  status: CheckStatus
  required: boolean
  evidence: string
  recommendation: string | null
  latency_ms: number | null
  observed_at: string
}

export interface CheckCounts {
  passed: number
  warning: number
  failed: number
  unknown: number
}

export interface DiagnosticRunListItem {
  id: string
  integration_id: string
  provider: IntegrationProvider
  trigger: string
  started_at: string
  completed_at: string | null
  overall_status: DiagnosticRunStatus
  summary: string | null
  check_counts: CheckCounts
}

export interface DiagnosticRun extends DiagnosticRunListItem {
  checks: DiagnosticCheck[]
}
