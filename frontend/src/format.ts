import type { CheckStatus, DiagnosticRunStatus, FailureSource, HealthState, Severity } from './types'

export function formatTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—'
}

export function formatMs(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value} ms`
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toLocaleString()
}

export const HEALTH_LABELS: Record<HealthState, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  failed: 'Failed',
  unknown: 'Unknown',
  not_configured: 'Not configured',
}

export const CHECK_LABELS: Record<DiagnosticRunStatus, string> = {
  pass: 'Pass',
  warning: 'Warning',
  fail: 'Fail',
  unknown: 'Unknown',
  running: 'Running',
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  info: 'Info',
  warning: 'Warning',
  error: 'Error',
  critical: 'Critical',
}

export const SOURCE_LABELS: Record<FailureSource, string> = {
  provider_request: 'Provider request',
  webhook_processing: 'Webhook processing',
  failure_lab: 'Failure Lab',
  diagnostic: 'Diagnostic',
}

export function checkLabel(status: CheckStatus | DiagnosticRunStatus): string {
  return CHECK_LABELS[status]
}
