import assert from 'node:assert/strict'
import test from 'node:test'
import type { InstrumentedHealth } from '../types'
import { attentionHeadline, telemetryFinding } from './copy.ts'

test('two degraded integrations use the approved headline', () => {
  assert.equal(attentionHeadline(0, 2, 3), 'Two integrations need attention.')
  assert.equal(attentionHeadline(0, 1, 3), 'One integration needs attention.')
  assert.equal(attentionHeadline(0, 3, 4), 'Three integrations need attention.')
  assert.equal(attentionHeadline(0, 0, 0), 'No integrations yet.')
  assert.equal(attentionHeadline(0, 0, 2), 'Nothing needs attention in this window.')
})

function health(overrides: Partial<InstrumentedHealth> & { metrics?: Partial<InstrumentedHealth['metrics']> }): InstrumentedHealth {
  return {
    integration_id: 'app',
    name: 'Orders',
    provider: 'instrumented_http',
    connection_status: 'instrumented',
    configuration: 'ready',
    health: 'degraded',
    summary: '3 of 5 SDK-reported observations failed in the last 24h.',
    evidence: [],
    recommended_action: null,
    last_activity_at: null,
    window_hours: 24,
    window_started_at: '2026-01-01T00:00:00Z',
    generated_at: '2026-01-02T00:00:00Z',
    provenance: 'sdk_reported',
    independently_verified: false,
    ...overrides,
    metrics: {
      request_count: 5,
      success_count: 2,
      error_count: 3,
      error_rate: 0.6,
      sample_count: 5,
      average_latency_ms: 40,
      p95_latency_ms: null,
      latest_occurred_at: '2026-01-02T00:00:00Z',
      latest_status_code: 200,
      latest_error_category: null,
      latest_duration_ms: 12,
      latest_route_template: '/ok',
      latest_service: 'orders',
      failure_categories: [],
      provenance: 'sdk_reported',
      independently_verified: false,
      ...overrides.metrics,
    },
  }
}

test('telemetry finding follows the latest report without hiding a degraded window', () => {
  assert.equal(telemetryFinding(health({})), 'The latest report succeeded.')
  assert.equal(
    telemetryFinding(health({ health: 'failed', metrics: { latest_status_code: 500, latest_error_category: 'http_server_error' } })),
    'The latest report failed.',
  )
  assert.equal(
    telemetryFinding(health({ health: 'unknown', metrics: { request_count: 0, error_count: 0, latest_status_code: null } })),
    'No observations in this window.',
  )
  assert.equal(telemetryFinding(health({ health: 'not_configured', metrics: { request_count: 0 } })), 'This application is not configured.')
})
