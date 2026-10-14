import assert from 'node:assert/strict'
import test from 'node:test'
import type { ProviderRequestLog, TelemetryEvent, WebhookEventSummary } from '../types'
import { httpTone, marksFromRequests, marksFromTelemetry, marksFromWebhooks, webhookTone } from './sequence.ts'

test('observation lamps follow status and category', () => {
  assert.equal(httpTone(200, null), 'ok')
  assert.equal(httpTone(429, 'rate_limited'), 'warn')
  assert.equal(httpTone(500, 'http_server_error'), 'bad')
  assert.equal(httpTone(null, 'timeout'), 'bad')
  assert.equal(httpTone(null, null), 'warn')
})

test('sequence keeps chronological order and dims filtered calls', () => {
  const events: TelemetryEvent[] = [
    event('b', '2026-01-02T00:00:00Z', 500, 'http_server_error', '/hang'),
    event('a', '2026-01-01T00:00:00Z', 200, null, '/ok'),
  ]
  const marks = marksFromTelemetry(events, {
    selectedId: 'a',
    dimmed: (item) => item.route_template !== '/ok',
  })
  assert.deepEqual(
    marks.map((mark) => [mark.id, mark.tone, mark.dimmed, mark.selected]),
    [
      ['a', 'ok', false, true],
      ['b', 'bad', true, false],
    ],
  )
})

test('a processed duplicate is hollow and a simulated request is dimmed', () => {
  const webhook = {
    id: 'wh_1',
    integration_id: 'stripe',
    provider: 'stripe',
    provider_event_id: 'evt',
    event_type: 'invoice.paid',
    provider_object_id: null,
    livemode: false,
    amount: null,
    currency: null,
    processing_status: 'processed',
    delivery_count: 2,
    attempt_count: 2,
    cycle_attempt_count: 1,
    retry_cycle: 0,
    manual_retry_count: 0,
    max_attempts: 5,
    next_attempt_at: null,
    first_received_at: '2026-01-01T00:00:00Z',
    last_received_at: '2026-01-01T00:00:00Z',
    processed_at: '2026-01-01T00:00:01Z',
    failed_at: null,
    dismissed_at: null,
    last_error_code: null,
    last_error_message: null,
  } satisfies WebhookEventSummary
  assert.equal(webhookTone(webhook), 'hollow')
  assert.equal(marksFromWebhooks([webhook])[0]?.detail, 'Duplicate absorbed')

  const request: ProviderRequestLog = {
    id: 'req_1',
    integration_id: 'gh',
    provider: 'github',
    method: 'GET',
    endpoint: '/user',
    status_code: 200,
    latency_ms: 10,
    timestamp: '2026-01-01T00:00:00Z',
    error_message: null,
    rate_limit_remaining: null,
    is_simulated: true,
    scenario: 'timeout',
  }
  const [mark] = marksFromRequests([request])
  assert.equal(mark?.dimmed, true)
  assert.equal(mark?.detail, 'Simulated')
  assert.equal(mark?.tone, 'hollow')
})

function event(
  id: string,
  occurredAt: string,
  status: number | null,
  category: TelemetryEvent['error_category'],
  route: string,
): TelemetryEvent {
  return {
    event_id: id,
    integration_id: 'app',
    occurred_at: occurredAt,
    received_at: occurredAt,
    kind: 'http_observation',
    service: 'orders',
    method: 'GET',
    route_template: route,
    status_code: status,
    duration_ms: 10,
    error_category: category,
    environment: 'local',
    provenance: 'sdk_reported',
    sdk_name: null,
    sdk_version: null,
    credential_id: null,
  }
}
