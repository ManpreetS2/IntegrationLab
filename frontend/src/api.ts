/** Thin HTTP helpers for talking to the FastAPI backend. */

import type {
  GitHubCheckResult,
  GitHubConnection,
  HealthResponse,
  Integration,
  IntegrationCreateRequest,
  ProviderRequestLog,
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
  limit?: number
}): Promise<ProviderRequestLog[]> {
  const search = new URLSearchParams()
  if (params?.provider) search.set('provider', params.provider)
  if (params?.integration_id) search.set('integration_id', params.integration_id)
  if (params?.limit) search.set('limit', String(params.limit))
  const query = search.toString()
  return request<ProviderRequestLog[]>(`/api/provider-requests${query ? `?${query}` : ''}`)
}

export { API_URL }
