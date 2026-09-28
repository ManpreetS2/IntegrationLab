/** Thin HTTP helpers for talking to the FastAPI backend. */

import type {
  HealthResponse,
  Integration,
  IntegrationCreateRequest,
} from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
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

export { API_URL }
