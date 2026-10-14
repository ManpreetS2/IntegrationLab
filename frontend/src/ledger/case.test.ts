import assert from 'node:assert/strict'
import test from 'node:test'
import type { FailureItem, TelemetryEvent } from '../types'
import { draftFromTelemetry, evidenceFor, supportCasePayload } from './case.ts'

function failure(overrides: Partial<FailureItem>): FailureItem {
  return {
    id: 'sdk_telemetry:event-1',
    source: 'sdk_telemetry',
    integration_id: 'app',
    integration_name: 'Orders',
    provider: 'instrumented_http',
    occurred_at: '2026-01-02T00:00:00Z',
    severity: 'error',
    code: 'timeout',
    summary: 'GET /hang timed out.',
    simulated: false,
    provenance: 'sdk_reported',
    service: 'orders',
    error_category: 'timeout',
    method: 'GET',
    endpoint: '/hang',
    status_code: null,
    latency_ms: 30000,
    webhook_event_id: null,
    event_type: null,
    attempt_count: null,
    diagnosis_title: null,
    retryable: null,
    diagnostic_run_id: null,
    ...overrides,
  }
}

test('SDK telemetry is summarized and never pinned', () => {
  const item = failure({})
  assert.equal(evidenceFor(item), null)
  const draft = draftFromTelemetry(
    {
      event_id: 'event-1',
      integration_id: 'app',
      occurred_at: '2026-01-02T00:00:00Z',
      received_at: '2026-01-02T00:00:01Z',
      kind: 'http_observation',
      service: 'orders',
      method: 'GET',
      route_template: '/ok',
      status_code: 200,
      duration_ms: 12,
      error_category: null,
      environment: 'local',
      provenance: 'sdk_reported',
      sdk_name: 'integrationlab',
      sdk_version: '0.1.0',
      credential_id: 'cred',
    } satisfies TelemetryEvent,
    undefined,
  )
  assert.equal(draft.evidence, null)
  const payload = supportCasePayload(draft, {
    title: draft.title,
    severity: draft.severity,
    impact: draft.impact,
    cause: draft.cause,
  })
  assert.equal(payload.source_evidence_type, undefined)
  assert.equal(payload.source_evidence_id, undefined)
  assert.equal('source_evidence_type' in payload, false)
  assert.match(draft.pinNote, /cannot be pinned/)
})

test('webhook and provider failures pin the supported evidence id', () => {
  const webhook = evidenceFor(
    failure({
      id: 'webhook:evt_1',
      source: 'webhook_processing',
      webhook_event_id: 'evt_1',
      provenance: null,
    }),
  )
  assert.deepEqual(webhook, { type: 'webhook_event', id: 'evt_1' })

  const request = evidenceFor(
    failure({
      id: 'provider_request:req_9',
      source: 'provider_request',
      provenance: null,
    }),
  )
  assert.deepEqual(request, { type: 'provider_request', id: 'req_9' })

  const draft = {
    integrationId: 'stripe',
    title: 'Missing object id',
    severity: 'SEV2' as const,
    impact: 'Processing failed.',
    cause: 'Missing data.object.id',
    evidence: webhook,
    pinNote: 'Pinned when the case is created: webhook_event.',
  }
  const payload = supportCasePayload(draft, {
    title: draft.title,
    severity: draft.severity,
    impact: draft.impact,
    cause: draft.cause,
  })
  assert.equal(payload.source_evidence_type, 'webhook_event')
  assert.equal(payload.source_evidence_id, 'evt_1')
})
