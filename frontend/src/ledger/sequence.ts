import type { FailureItem, ProviderRequestLog, TelemetryEvent, WebhookEventSummary } from '../types'

export interface SequenceMark {
  id: string
  tone: 'ok' | 'warn' | 'bad' | 'hollow'
  title: string
  detail: string
  dimmed: boolean
  selected: boolean
}

export function httpTone(status: number | null, category: string | null): SequenceMark['tone'] {
  if (category === 'timeout' || category === 'http_server_error' || category === 'transport_error') return 'bad'
  if (category === 'rate_limited' || category === 'http_client_error') return 'warn'
  if (status === null) return 'warn'
  if (status >= 500) return 'bad'
  if (status === 429 || status >= 400) return 'warn'
  return 'ok'
}

export function webhookTone(event: WebhookEventSummary): SequenceMark['tone'] {
  if (event.processing_status === 'failed') return 'bad'
  if (
    event.processing_status === 'retry_scheduled' ||
    event.processing_status === 'pending' ||
    event.processing_status === 'processing'
  ) {
    return 'warn'
  }
  if (event.processing_status === 'processed' && event.delivery_count > 1) return 'hollow'
  if (event.processing_status === 'processed') return 'ok'
  return 'hollow'
}

export function marksFromTelemetry(
  events: TelemetryEvent[],
  options?: { selectedId?: string | null; dimmed?: (event: TelemetryEvent) => boolean },
): SequenceMark[] {
  return [...events]
    .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at))
    .map((event) => ({
      id: event.event_id,
      tone: httpTone(event.status_code, event.error_category),
      title: `${event.method} ${event.route_template}`,
      detail:
        event.status_code !== null
          ? `HTTP ${event.status_code}`
          : (event.error_category?.replaceAll('_', ' ') ?? 'No status'),
      dimmed: options?.dimmed?.(event) ?? false,
      selected: options?.selectedId === event.event_id,
    }))
}

export function marksFromWebhooks(events: WebhookEventSummary[], selectedId?: string | null): SequenceMark[] {
  return [...events]
    .sort((a, b) => a.last_received_at.localeCompare(b.last_received_at))
    .map((event) => ({
      id: event.id,
      tone: webhookTone(event),
      title: event.event_type,
      detail:
        event.processing_status === 'failed'
          ? (event.last_error_code ?? 'Failed')
          : event.processing_status === 'processed' && event.delivery_count > 1
            ? 'Duplicate absorbed'
            : event.processing_status.replaceAll('_', ' '),
      dimmed: false,
      selected: selectedId === event.id,
    }))
}

export function marksFromRequests(requests: ProviderRequestLog[], selectedId?: string | null): SequenceMark[] {
  return [...requests]
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .map((item) => ({
      id: item.id,
      tone: item.is_simulated ? 'hollow' : httpTone(item.status_code, null),
      title: `${item.method} ${item.endpoint}`,
      detail: item.is_simulated ? 'Simulated' : item.status_code !== null ? `HTTP ${item.status_code}` : 'No status',
      dimmed: item.is_simulated,
      selected: selectedId === item.id,
    }))
}

export function sequenceFocusForFailure(item: FailureItem): { kind: 'telemetry' | 'webhook' | 'request' | 'none'; id: string | null } {
  if (item.source === 'sdk_telemetry' && item.id.startsWith('sdk_telemetry:')) {
    return { kind: 'telemetry', id: item.id.slice('sdk_telemetry:'.length) }
  }
  if (item.source === 'webhook_processing') return { kind: 'webhook', id: item.webhook_event_id }
  if (item.source === 'provider_request') {
    const id = item.id.includes(':') ? item.id.split(':').pop()! : item.id
    return { kind: 'request', id }
  }
  return { kind: 'none', id: null }
}
