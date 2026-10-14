import assert from 'node:assert/strict'
import test from 'node:test'
import type { IntegrationHealth } from '../types'
import { integrationStations } from './trail.ts'

test('evidence trail stays short and does not invent a pin', () => {
  const item: IntegrationHealth = {
    integration_id: 'app',
    name: 'Orders',
    provider: 'instrumented_http',
    connection_status: 'instrumented',
    configuration: 'ready',
    health: 'degraded',
    summary: '3 of 5 SDK-reported observations failed in the last 24h. The latest request succeeded.',
    evidence: ['A much longer stored paragraph that should not be copied verbatim into every station of the trail.'],
    recommended_action: 'Inspect the failing routes.',
    last_activity_at: null,
    last_checked_at: null,
    request_metrics: null,
    webhook_metrics: null,
    latest_diagnostic: null,
    telemetry_metrics: {
      request_count: 5,
      success_count: 2,
      error_count: 3,
      error_rate: 0.6,
      sample_count: 5,
      average_latency_ms: 40,
      p95_latency_ms: null,
      latest_occurred_at: null,
      latest_status_code: 200,
      latest_error_category: null,
      latest_duration_ms: 12,
      latest_route_template: '/ok',
      latest_service: 'orders',
      failure_categories: [],
      provenance: 'sdk_reported',
      independently_verified: false,
    },
  }
  const stations = integrationStations(item, 24)
  assert.ok(stations.length <= 5)
  for (const station of stations) assert.ok(station.text.length <= 180, station.text)
  assert.ok(stations.some((station) => station.text.includes('sdk_reported')))
  assert.equal(stations.some((station) => /pinned/i.test(station.text)), false)
})
