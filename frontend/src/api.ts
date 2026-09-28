/** Thin HTTP helpers for talking to the FastAPI backend. */

import type {
  FailureLabRun,
  FailureLabRunListItem,
  FailureScenarioId,
  FailureScenarioInfo,
  GitHubCheckResult,
  GitHubConnection,
  HealthResponse,
  Integration,
  IntegrationCreateRequest,
  ProcessDueResult,
  ProviderRequestLog,
  WebhookEventDetail,
  WebhookEventSummary,
  WebhookProcessingStatus,
  WebhookSummary,
} from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Default Content-Type first, then merge caller headers so they can
  // intentionally override without wiping the helper defaults via spread order.
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (init?.headers) {
    new Headers(init.headers).forEach((value, key) => {
      headers.set(key, value)
    })
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
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

export { API_URL }
