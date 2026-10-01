/** Thin HTTP helpers for talking to the FastAPI backend. */

import { getOperatorApiKey } from './auth'
import type {
  DiagnosticRun,
  DiagnosticRunListItem,
  FailureItem,
  FailureLabRun,
  FailureLabRunListItem,
  FailureScenarioId,
  FailureScenarioInfo,
  FailureSource,
  GitHubCheckResult,
  GitHubConnection,
  HealthResponse,
  Integration,
  CaseSeverity,
  CaseStatus,
  EvidenceType,
  IntegrationCreateRequest,
  IntegrationProvider,
  IntegrationReliabilityDetail,
  OperatorAuditEvent,
  ProcessDueResult,
  ProviderRequestLog,
  ReliabilityOverview,
  RequestMetricsResponse,
  SupportCase,
  SupportCaseDetail,
  SupportCaseEvidence,
  SupportCaseNote,
  SystemHealth,
  TimelineItem,
  WebhookEventDetail,
  WebhookEventSummary,
  WebhookProcessingStatus,
  WebhookSummary,
} from './types'

export interface OperatorAuthStatus {
  required: boolean
}

/**
 * API base URL.
 *
 * - Local Vite: unset → http://localhost:8000
 * - Production CloudFront: VITE_API_URL="" → same-origin relative paths
 * - Explicit override: any non-null VITE_API_URL value wins (including "")
 */
function resolveApiUrl(): string {
  const configured = import.meta.env.VITE_API_URL
  if (configured !== undefined && configured !== null) {
    return String(configured)
  }
  return 'http://localhost:8000'
}

const API_URL = resolveApiUrl()

/** Absolute base for display / copy-paste (never empty). */
export function apiOrigin(): string {
  if (API_URL) return API_URL
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  return ''
}

/** Non-2xx response from the API. `message` keeps the raw detail text for existing callers. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function toQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (init?.headers) {
    new Headers(init.headers).forEach((value, key) => {
      headers.set(key, value)
    })
  }

  // Never bake the operator key into frontend assets. It is entered at runtime,
  // stored in sessionStorage, and attached only to operator /api requests.
  if (path.startsWith('/api/')) {
    const operatorKey = getOperatorApiKey()
    if (operatorKey) headers.set('Authorization', `Bearer ${operatorKey}`)
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new ApiError(response.status, detail || `Request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function getOperatorAuthStatus(): Promise<OperatorAuthStatus> {
  return request<OperatorAuthStatus>('/auth/operator')
}

export function verifyOperatorAccess(): Promise<{ authorized: boolean }> {
  return request<{ authorized: boolean }>('/api/auth/check')
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export function listIntegrations(): Promise<Integration[]> {
  return request<Integration[]>('/api/integrations')
}

export function createIntegration(
  payload: IntegrationCreateRequest,
): Promise<Integration> {
  return request<Integration>('/api/integrations', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function githubConnectUrl(integrationId: string): string {
  return `${API_URL}/api/integrations/${integrationId}/github/connect`
}

export function getGitHubConnection(integrationId: string): Promise<GitHubConnection> {
  return request<GitHubConnection>(`/api/integrations/${integrationId}/github`)
}

export function checkGitHubConnection(integrationId: string): Promise<GitHubCheckResult> {
  return request<GitHubCheckResult>(`/api/integrations/${integrationId}/github/check`, {
    method: 'POST',
  })
}

export function listProviderRequests(params?: {
  provider?: string
  integration_id?: string
  is_simulated?: boolean
  scenario?: string
  limit?: number
}): Promise<ProviderRequestLog[]> {
  const search = new URLSearchParams()
  if (params?.provider) search.set('provider', params.provider)
  if (params?.integration_id) search.set('integration_id', params.integration_id)
  if (params?.is_simulated !== undefined) search.set('is_simulated', String(params.is_simulated))
  if (params?.scenario) search.set('scenario', params.scenario)
  if (params?.limit) search.set('limit', String(params.limit))
  const query = search.toString()
  return request<ProviderRequestLog[]>(`/api/provider-requests${query ? `?${query}` : ''}`)
}

export function listFailureScenarios(): Promise<FailureScenarioInfo[]> {
  return request<FailureScenarioInfo[]>('/api/failure-lab/scenarios')
}

export function runFailureScenario(payload: {
  integration_id: string
  scenario: FailureScenarioId
}): Promise<FailureLabRun> {
  return request<FailureLabRun>('/api/failure-lab/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listFailureRuns(params?: {
  integration_id?: string
  scenario?: FailureScenarioId
  limit?: number
}): Promise<FailureLabRunListItem[]> {
  const search = new URLSearchParams()
  if (params?.integration_id) search.set('integration_id', params.integration_id)
  if (params?.scenario) search.set('scenario', params.scenario)
  if (params?.limit) search.set('limit', String(params.limit))
  const query = search.toString()
  return request<FailureLabRunListItem[]>(`/api/failure-lab/runs${query ? `?${query}` : ''}`)
}

export function getFailureRun(runId: string): Promise<FailureLabRun> {
  return request<FailureLabRun>(`/api/failure-lab/runs/${runId}`)
}

const WEBHOOKS = '/api/webhooks/stripe'

export function getWebhookSummary(): Promise<WebhookSummary> {
  return request<WebhookSummary>(`${WEBHOOKS}/summary`)
}

export function listWebhookEvents(params?: {
  status?: WebhookProcessingStatus
  event_type?: string
  integration_id?: string
  limit?: number
}): Promise<WebhookEventSummary[]> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.event_type) search.set('event_type', params.event_type)
  if (params?.integration_id) search.set('integration_id', params.integration_id)
  if (params?.limit) search.set('limit', String(params.limit))
  const query = search.toString()
  return request<WebhookEventSummary[]>(`${WEBHOOKS}/events${query ? `?${query}` : ''}`)
}

export function listFailedWebhookEvents(limit = 50): Promise<WebhookEventSummary[]> {
  return request<WebhookEventSummary[]>(`${WEBHOOKS}/failed?limit=${limit}`)
}

export function getWebhookEvent(eventId: string): Promise<WebhookEventDetail> {
  return request<WebhookEventDetail>(`${WEBHOOKS}/events/${eventId}`)
}

export function processWebhookEvent(eventId: string): Promise<WebhookEventDetail> {
  return request<WebhookEventDetail>(`${WEBHOOKS}/events/${eventId}/process`, { method: 'POST' })
}

export function retryWebhookEvent(eventId: string): Promise<WebhookEventDetail> {
  return request<WebhookEventDetail>(`${WEBHOOKS}/events/${eventId}/retry`, { method: 'POST' })
}

export function dismissWebhookEvent(eventId: string): Promise<WebhookEventDetail> {
  return request<WebhookEventDetail>(`${WEBHOOKS}/events/${eventId}/dismiss`, { method: 'POST' })
}

export function processDueWebhookEvents(limit = 25): Promise<ProcessDueResult> {
  return request<ProcessDueResult>(`${WEBHOOKS}/process-due?limit=${limit}`, { method: 'POST' })
}

// ------------------------------------------------------------ reliability

const RELIABILITY = '/api/reliability'

export function getReliabilitySystem(): Promise<SystemHealth> {
  return request<SystemHealth>(`${RELIABILITY}/system`)
}

export function getReliabilityOverview(windowHours = 24): Promise<ReliabilityOverview> {
  return request<ReliabilityOverview>(`${RELIABILITY}/overview${toQuery({ window_hours: windowHours })}`)
}

export function getIntegrationReliability(integrationId: string): Promise<IntegrationReliabilityDetail> {
  return request<IntegrationReliabilityDetail>(`${RELIABILITY}/integrations/${integrationId}`)
}

export function listReliabilityFailures(params: {
  provider?: IntegrationProvider
  integration_id?: string
  source?: FailureSource
  include_simulated?: boolean
  window_hours?: number
  limit?: number
}): Promise<FailureItem[]> {
  return request<FailureItem[]>(`${RELIABILITY}/failures${toQuery(params)}`)
}

export function getRequestMetrics(params: {
  provider?: string
  integration_id?: string
  is_simulated?: boolean
  window_hours?: number
}): Promise<RequestMetricsResponse> {
  return request<RequestMetricsResponse>(`${RELIABILITY}/request-metrics${toQuery(params)}`)
}

// ------------------------------------------------------------ diagnostics

export function runDiagnostics(integrationId: string): Promise<DiagnosticRun> {
  return request<DiagnosticRun>(`/api/diagnostics/${integrationId}/run`, { method: 'POST' })
}

export function listDiagnosticRuns(integrationId: string, limit = 20): Promise<DiagnosticRunListItem[]> {
  return request<DiagnosticRunListItem[]>(`/api/diagnostics/${integrationId}/runs${toQuery({ limit })}`)
}

export function getDiagnosticRun(runId: string): Promise<DiagnosticRun> {
  return request<DiagnosticRun>(`/api/diagnostics/runs/${runId}`)
}

// ------------------------------------------------------------ support operations

export function listSupportCases(params?: {
  status?: CaseStatus
  severity?: CaseSeverity
  integration_id?: string
  environment?: string
  open_only?: boolean
}): Promise<SupportCase[]> {
  return request<SupportCase[]>(`/api/support-cases${toQuery(params ?? {})}`)
}

export function createSupportCase(payload: {
  integration_id: string
  title: string
  severity?: CaseSeverity
  impact_summary?: string
  suspected_cause?: string
  source_evidence_type?: EvidenceType
  source_evidence_id?: string
}): Promise<SupportCaseDetail> {
  return request<SupportCaseDetail>('/api/support-cases', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getSupportCase(caseId: string): Promise<SupportCaseDetail> {
  return request<SupportCaseDetail>(`/api/support-cases/${caseId}`)
}

export function updateSupportCase(
  caseId: string,
  payload: Partial<{
    title: string
    severity: CaseSeverity
    status: CaseStatus
    owner: string
    impact_summary: string
    suspected_cause: string
    confirmed_root_cause: string
    mitigation_summary: string
    resolution_summary: string
  }>,
): Promise<SupportCaseDetail> {
  return request<SupportCaseDetail>(`/api/support-cases/${caseId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function getSupportCaseTimeline(caseId: string): Promise<TimelineItem[]> {
  return request<TimelineItem[]>(`/api/support-cases/${caseId}/timeline`)
}

export function addSupportCaseNote(caseId: string, body: string): Promise<SupportCaseNote> {
  return request<SupportCaseNote>(`/api/support-cases/${caseId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function pinSupportCaseEvidence(
  caseId: string,
  payload: { evidence_type: EvidenceType; evidence_id: string; safe_label?: string },
): Promise<SupportCaseEvidence> {
  return request<SupportCaseEvidence>(`/api/support-cases/${caseId}/evidence`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listAuditEvents(params?: {
  action?: string
  integration_id?: string
  support_case_id?: string
  correlation_id?: string
  limit?: number
}): Promise<OperatorAuditEvent[]> {
  return request<OperatorAuditEvent[]>(`/api/audit-events${toQuery(params ?? {})}`)
}

export { API_URL }
