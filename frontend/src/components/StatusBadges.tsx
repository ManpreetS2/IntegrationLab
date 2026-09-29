import { CHECK_LABELS, HEALTH_LABELS, SEVERITY_LABELS } from '../format'
import type { DiagnosticRunStatus, HealthState, Severity } from '../types'

export function HealthBadge({ state }: { state: HealthState }) {
  return <span className={`badge health-${state}`}>{HEALTH_LABELS[state]}</span>
}

export function CheckBadge({ status }: { status: DiagnosticRunStatus }) {
  return <span className={`badge check-${status}`}>{CHECK_LABELS[status]}</span>
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`badge severity-${severity}`}>{SEVERITY_LABELS[severity]}</span>
}
