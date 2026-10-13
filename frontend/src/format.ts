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
  sdk_telemetry: 'SDK-reported',
}

/** Null means there were no observations. That is unavailable, not a 0% error rate. */
export function formatErrorRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return 'Unavailable'
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(rate * 100)}%`
}

/** p95 is withheld until the contract's 20-sample minimum. */
export function formatP95(value: number | null | undefined, sampleCount: number): string {
  if (sampleCount < 20 || value === null || value === undefined) return 'Unavailable'
  return formatMs(value)
}

export function formatProvider(provider: string): string {
  if (provider === 'github') return 'GitHub'
  if (provider === 'stripe') return 'Stripe'
  if (provider === 'instrumented_http') return 'Instrumented HTTP'
  return provider
}

export function formatIntegrationStatus(status: string): string {
  if (status === 'registered') return 'Registered'
  if (status === 'instrumented') return 'Instrumented'
  if (status === 'not_connected') return 'Not connected'
  if (status === 'needs_setup') return 'Needs setup'
  if (status === 'connected') return 'Connected'
  return status
}

export function checkLabel(status: CheckStatus | DiagnosticRunStatus): string {
  return CHECK_LABELS[status]
}
