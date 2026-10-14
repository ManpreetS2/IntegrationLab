import { formatProvider, formatTime, HEALTH_LABELS } from '../format.ts'
import type { HealthState, IntegrationHealth, InstrumentedHealth } from '../types'

const SMALL = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']

function countWord(count: number, lower = false): string {
  const word = count >= 0 && count < SMALL.length ? SMALL[count] : String(count)
  return lower ? word.toLowerCase() : word
}

/** Headline from overview totals. Wording stays numeric past nine. */
export function attentionHeadline(failed: number, degraded: number, integrationCount: number): string {
  if (integrationCount === 0) return 'No integrations yet.'
  if (failed > 0 && degraded > 0) {
    return `${countWord(failed)} failed and ${countWord(degraded, true)} degraded.`
  }
  if (failed === 1) return 'One integration has failed.'
  if (failed > 1) return `${countWord(failed)} integrations have failed.`
  if (degraded === 1) return 'One integration needs attention.'
  if (degraded > 1) return `${countWord(degraded)} integrations need attention.`
  return 'Nothing needs attention in this window.'
}

export function telemetryFinding(health: InstrumentedHealth): string {
  if (health.health === 'not_configured') return 'This application is not configured.'
  const latestFailed =
    health.metrics.latest_error_category != null ||
    (health.metrics.latest_status_code !== null && health.metrics.latest_status_code >= 400)
  const latestSucceeded =
    health.metrics.request_count > 0 &&
    health.metrics.latest_status_code !== null &&
    health.metrics.latest_status_code < 400 &&
    !latestFailed
  if (health.metrics.request_count === 0 || health.health === 'unknown') return 'No observations in this window.'
  if (latestSucceeded) return 'The latest report succeeded.'
  if (latestFailed) return 'The latest report failed.'
  return health.summary
}

export function failureFinding(item: { code: string } | null, total: number): string {
  if (!item) return total === 0 ? 'No failures in this window.' : 'Select a failure.'
  return item.code
}

export function shorten(text: string, max = 160): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, max - 1).trimEnd()}…`
}

/**
 * Empty observation sequence. A Stripe failed queue is persistent and is not
 * the same thing as a delivery inside the selected window.
 */
export function emptyWindowSequence(item: IntegrationHealth | null): string {
  const webhooks = item?.provider === 'stripe' ? item.webhook_metrics : null
  if (webhooks && webhooks.events_in_window === 0 && webhooks.failed > 0) {
    const noun = webhooks.failed === 1 ? 'event' : 'events'
    return `No deliveries in this window. The failed queue still holds ${webhooks.failed} ${noun} from earlier. They are not recent deliveries.`
  }
  return 'No observations in this window.'
}

export function windowTally(item: IntegrationHealth): string {
  const telemetry = item.telemetry_metrics
  if (telemetry) {
    if (telemetry.request_count === 0) return 'No observations'
    return `${telemetry.error_count} of ${telemetry.request_count} failed`
  }
  const webhooks = item.webhook_metrics
  if (webhooks) {
    if (webhooks.events_in_window === 0) return webhooks.failed > 0 ? 'No deliveries' : 'No events'
    return `${webhooks.failed} failed · ${webhooks.duplicate_deliveries} duplicates`
  }
  const requests = item.request_metrics
  if (requests) {
    if (requests.request_count === 0) return 'No requests'
    return `${requests.failure_count} of ${requests.request_count} failed`
  }
  return 'No activity'
}

export function latestActivity(item: IntegrationHealth): string {
  const telemetry = item.telemetry_metrics
  if (telemetry && (telemetry.latest_route_template || telemetry.latest_status_code !== null)) {
    const status = telemetry.latest_status_code ?? telemetry.latest_error_category ?? '—'
    const route = telemetry.latest_route_template ?? telemetry.latest_service ?? 'observation'
    return `${route} · ${status}`
  }
  const requests = item.request_metrics
  if (requests?.latest_request_at) {
    const status = requests.latest_status_code ?? requests.latest_error_code ?? '—'
    return `${requests.latest_endpoint ?? 'request'} · ${status}`
  }
  if (item.webhook_metrics?.last_received_at) return formatTime(item.webhook_metrics.last_received_at)
  if (item.last_activity_at) return formatTime(item.last_activity_at)
  return 'None in this window'
}

export function whyRows(item: IntegrationHealth): [string, string][] {
  return [
    ['Health', HEALTH_LABELS[item.health]],
    ['Provider', formatProvider(item.provider)],
    ['Latest', latestActivity(item)],
    ['Window', windowTally(item)],
  ]
}

export type OverviewFilter = 'all' | 'attention' | 'sdk' | 'webhook' | 'quiet'

export function matchesOverviewFilter(item: IntegrationHealth, filter: OverviewFilter): boolean {
  if (filter === 'attention') return item.health === 'degraded' || item.health === 'failed'
  if (filter === 'sdk') return item.provider === 'instrumented_http'
  if (filter === 'webhook') return item.provider === 'stripe'
  if (filter === 'quiet') return item.health === 'not_configured'
  return true
}

export function healthTone(state: HealthState): 'ok' | 'warn' | 'bad' | 'hollow' {
  if (state === 'healthy') return 'ok'
  if (state === 'degraded') return 'warn'
  if (state === 'failed') return 'bad'
  return 'hollow'
}
