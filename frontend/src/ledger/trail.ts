import { formatErrorRate, formatMs, formatP95, SOURCE_LABELS } from '../format.ts'
import type { FailureItem, InstrumentedHealth, IntegrationHealth, TelemetryEvent } from '../types'
import { evidenceFor } from './case.ts'
import { shorten } from './copy.ts'

export interface TrailStation {
  label: string
  text: string
}

export function integrationStations(item: IntegrationHealth, windowHours: number): TrailStation[] {
  const stations: TrailStation[] = [{ label: 'State', text: shorten(item.summary, 140) }]
  const telemetry = item.telemetry_metrics
  if (telemetry) {
    stations.push({
      label: 'Window',
      text:
        telemetry.request_count === 0
          ? `No SDK observations in the last ${windowHours}h.`
          : `${telemetry.error_count} of ${telemetry.request_count} SDK observations failed. Error rate ${formatErrorRate(telemetry.error_rate)}. p95 ${formatP95(telemetry.p95_latency_ms, telemetry.sample_count)}.`,
    })
    stations.push({ label: 'Provenance', text: 'sdk_reported. Not independently verified.' })
  }
  const webhooks = item.webhook_metrics
  if (webhooks) {
    stations.push({
      label: 'Queue',
      text: `${webhooks.failed} failed · ${webhooks.pending} pending · ${webhooks.duplicate_deliveries} duplicates absorbed.`,
    })
  }
  const requests = item.request_metrics
  if (requests) {
    stations.push({
      label: 'Requests',
      text:
        requests.request_count === 0
          ? `No real provider requests in the last ${windowHours}h.`
          : `${requests.failure_count} of ${requests.request_count} real requests failed. Latest ${requests.latest_status_code ?? requests.latest_error_code ?? '—'}.`,
    })
  }
  if (item.recommended_action) stations.push({ label: 'Next', text: shorten(item.recommended_action, 140) })
  return stations.slice(0, 5)
}

export function telemetryStations(
  event: TelemetryEvent | null,
  health: InstrumentedHealth | undefined,
  credentialPrefix: string | null,
): TrailStation[] {
  const stations: TrailStation[] = []
  if (health) {
    stations.push({ label: 'Health', text: shorten(health.summary, 140) })
    const metrics = health.metrics
    stations.push({
      label: 'Window',
      text:
        metrics.request_count === 0
          ? `No SDK observations in the last ${health.window_hours}h.`
          : `${metrics.error_count} of ${metrics.request_count} failed. Error rate ${formatErrorRate(metrics.error_rate)}. p95 ${formatP95(metrics.p95_latency_ms, metrics.sample_count)}.`,
    })
  }
  if (event) {
    const status = event.status_code !== null ? `HTTP ${event.status_code}` : 'No status'
    stations.push({
      label: 'Observation',
      text: `${event.method} ${event.route_template} · ${status} · ${formatMs(event.duration_ms)}`,
    })
  }
  stations.push({
    label: 'Provenance',
    text: 'sdk_reported. Not independently verified. Not pinned as evidence.',
  })
  if (credentialPrefix) {
    stations.push({ label: 'Credential', text: `Active prefix ${credentialPrefix}. The secret is not shown.` })
  }
  return stations.slice(0, 5)
}

export function failureStations(item: FailureItem): TrailStation[] {
  const evidence = evidenceFor(item)
  const where = [item.service, item.method, item.endpoint ?? item.event_type, item.status_code !== null ? `HTTP ${item.status_code}` : null]
    .filter(Boolean)
    .join(' · ')
  const stations: TrailStation[] = [{ label: 'Fault', text: shorten(item.summary, 140) }]
  if (where) stations.push({ label: 'Where', text: where })
  stations.push({
    label: 'Source',
    text: item.simulated ? 'Failure Lab simulation. Excluded from health.' : SOURCE_LABELS[item.source],
  })
  stations.push({
    label: 'Evidence',
    text:
      item.source === 'sdk_telemetry'
        ? 'Included in the case summary only. SDK telemetry cannot be pinned.'
        : evidence
          ? `Can pin ${evidence.type}.`
          : 'No evidence id is available to pin.',
  })
  return stations
}
