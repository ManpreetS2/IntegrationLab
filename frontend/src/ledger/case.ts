import type { CaseSeverity, Environment, EvidenceType, FailureItem, FailureSource, InstrumentedHealth, IntegrationHealth, Severity, TelemetryEvent } from '../types'
import { shorten } from './copy.ts'

export interface CaseEvidenceRef {
  type: EvidenceType
  id: string
}

export interface CaseDraft {
  integrationId: string
  environment?: Environment
  title: string
  severity: CaseSeverity
  impact: string
  cause: string
  evidence: CaseEvidenceRef | null
  pinNote: string
}

export interface SupportCasePayload {
  integration_id: string
  title: string
  severity: CaseSeverity
  impact_summary?: string
  suspected_cause?: string
  environment?: Environment
  source_evidence_type?: EvidenceType
  source_evidence_id?: string
}

/** Pin only evidence types the support-case contract accepts. SDK telemetry is never a pin. */
export function evidenceFor(item: FailureItem): CaseEvidenceRef | null {
  if (item.source === 'failure_lab' && item.id.startsWith('failure_lab:')) {
    return { type: 'failure_lab_run', id: item.id.slice('failure_lab:'.length) }
  }
  if (item.source === 'diagnostic' && item.diagnostic_run_id) {
    return { type: 'diagnostic_run', id: item.diagnostic_run_id }
  }
  if (item.source === 'webhook_processing' && item.webhook_event_id) {
    return { type: 'webhook_event', id: item.webhook_event_id }
  }
  if (item.source === 'provider_request' && item.id) {
    const id = item.id.includes(':') ? item.id.split(':').pop()! : item.id
    return { type: 'provider_request', id }
  }
  return null
}

export function severityForFailure(severity: Severity): CaseSeverity {
  if (severity === 'critical') return 'SEV1'
  if (severity === 'error') return 'SEV2'
  if (severity === 'warning') return 'SEV3'
  return 'SEV4'
}

export function failureTitle(item: FailureItem): string {
  if (item.simulated) return `Simulated failure: ${item.code}`
  if (item.source === 'sdk_telemetry') return `SDK-reported observation: ${item.code}`
  if (item.source === 'provider_request' && item.status_code === 401) return 'GitHub authentication failure observed'
  const source = item.source as FailureSource
  const labels: Record<FailureSource, string> = {
    provider_request: 'Provider request',
    webhook_processing: 'Webhook processing',
    failure_lab: 'Failure Lab',
    diagnostic: 'Diagnostic',
    sdk_telemetry: 'SDK-reported',
  }
  return `${labels[source] ?? item.source}: ${item.code}`
}

export function draftFromFailure(item: FailureItem, environment?: Environment): CaseDraft | null {
  if (!item.integration_id) return null
  const evidence = evidenceFor(item)
  let pinNote = 'No evidence id is available to pin.'
  if (item.source === 'sdk_telemetry') {
    pinNote = 'SDK telemetry is included in the summary only. It cannot be pinned as evidence.'
  } else if (evidence) {
    pinNote = `Pinned when the case is created: ${evidence.type}.`
  }
  return {
    integrationId: item.integration_id,
    environment,
    title: shorten(failureTitle(item), 200),
    severity: severityForFailure(item.severity),
    impact: item.summary,
    cause: item.simulated ? 'Failure Lab simulation. Not a live incident.' : item.summary,
    evidence,
    pinNote,
  }
}

export function draftFromIntegration(item: IntegrationHealth): CaseDraft {
  let severity: CaseSeverity = 'SEV4'
  if (item.health === 'failed') severity = 'SEV2'
  else if (item.health === 'degraded') severity = 'SEV3'
  return {
    integrationId: item.integration_id,
    title: shorten(`${item.name}: ${item.summary}`, 200),
    severity,
    impact: item.summary,
    cause: item.recommended_action ?? item.summary,
    evidence: null,
    pinNote: 'Opened from the integration record. No single observation is pinned.',
  }
}

export function draftFromTelemetry(event: TelemetryEvent, health: InstrumentedHealth | undefined): CaseDraft {
  const failed = event.error_category != null || (event.status_code !== null && event.status_code >= 400)
  const title = failed
    ? `SDK-reported ${event.method} ${event.route_template} failed`
    : `SDK-reported ${event.method} ${event.route_template} in a ${health?.health ?? 'reported'} window`
  const cause = failed
    ? [event.error_category, event.status_code !== null ? `HTTP ${event.status_code}` : null].filter(Boolean).join(' · ')
    : 'The selected observation succeeded. The case summarizes the window, not a failed call.'
  return {
    integrationId: event.integration_id,
    environment: event.environment,
    title: shorten(title, 200),
    severity: failed && ((event.status_code ?? 0) >= 500 || event.error_category === 'timeout') ? 'SEV2' : 'SEV3',
    impact: health?.summary ?? `${event.method} ${event.route_template}`,
    cause,
    evidence: null,
    pinNote: 'SDK telemetry is included in the summary only. It cannot be pinned as evidence.',
  }
}

export function supportCasePayload(
  draft: CaseDraft,
  fields: { title: string; severity: CaseSeverity; impact: string; cause: string },
): SupportCasePayload {
  const payload: SupportCasePayload = {
    integration_id: draft.integrationId,
    title: fields.title.trim().slice(0, 200),
    severity: fields.severity,
    impact_summary: fields.impact.trim() || undefined,
    suspected_cause: fields.cause.trim() || undefined,
    environment: draft.environment,
  }
  if (draft.evidence) {
    payload.source_evidence_type = draft.evidence.type
    payload.source_evidence_id = draft.evidence.id
  }
  return payload
}
