import { formatCount, formatMs, formatTime } from '../format'
import { pageHref } from '../hooks'
import type { IntegrationHealth, RequestMetrics, WebhookMetrics } from '../types'
import { CheckBadge, HealthBadge } from './StatusBadges'

function latestRequestText(metrics: RequestMetrics): string {
  if (!metrics.latest_request_at) return '—'
  const outcome =
    metrics.latest_status_code !== null ? `HTTP ${metrics.latest_status_code}` : (metrics.latest_error_code ?? '—')
  const band =
    metrics.latest_latency_band && metrics.latest_latency_band !== 'normal' ? ` (${metrics.latest_latency_band})` : ''
  return `${outcome} · ${formatMs(metrics.latest_latency_ms)}${band}`
}

function GitHubFacts({ metrics, windowHours }: { metrics: RequestMetrics; windowHours: number }) {
  return (
    <dl className="fact-grid">
      <div>
        <dt>Real requests ({windowHours}h)</dt>
        <dd>
          {metrics.request_count === 0
            ? 'None'
            : `${metrics.failure_count} / ${metrics.request_count} failed`}
        </dd>
      </div>
      <div>
        <dt>Latest</dt>
        <dd>{latestRequestText(metrics)}</dd>
      </div>
      <div>
        <dt>p95 latency</dt>
        <dd>{formatMs(metrics.p95_latency_ms)}</dd>
      </div>
      <div>
        <dt>Rate limit remaining</dt>
        <dd>{formatCount(metrics.rate_limit_remaining)}</dd>
      </div>
    </dl>
  )
}

function StripeFacts({ metrics, windowHours }: { metrics: WebhookMetrics; windowHours: number }) {
  return (
    <dl className="fact-grid">
      <div>
        <dt>Events ({windowHours}h / total)</dt>
        <dd>
          {metrics.events_in_window} / {metrics.events_total}
        </dd>
      </div>
      <div>
        <dt>Pending · Retry · Failed</dt>
        <dd>
          {metrics.pending} · {metrics.retry_scheduled} · {metrics.failed}
        </dd>
      </div>
      <div>
        <dt>Duplicates absorbed</dt>
        <dd>{metrics.duplicate_deliveries}</dd>
      </div>
      <div>
        <dt>Last delivery</dt>
        <dd>{formatTime(metrics.last_received_at)}</dd>
      </div>
    </dl>
  )
}

function IntegrationHealthCard({ item, windowHours }: { item: IntegrationHealth; windowHours: number }) {
  return (
    <article className={`health-card health-card-${item.health}`}>
      <header className="health-card-header">
        <div>
          <h3>{item.name}</h3>
          <p className="muted small-text">
            <span className="provider-cell">{item.provider}</span> · {item.configuration}
          </p>
        </div>
        <HealthBadge state={item.health} />
      </header>

      <p className="health-summary">{item.summary}</p>

      {item.request_metrics ? <GitHubFacts metrics={item.request_metrics} windowHours={windowHours} /> : null}
      {item.webhook_metrics ? <StripeFacts metrics={item.webhook_metrics} windowHours={windowHours} /> : null}

      {item.evidence.length > 0 ? (
        <ul className="evidence-list">
          {item.evidence.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}

      {item.recommended_action ? (
        <p className="recommendation">
          <strong>Next step:</strong> {item.recommended_action}
        </p>
      ) : null}

      <footer className="health-card-footer">
        <span className="muted small-text">
          Last diagnostic:{' '}
          {item.latest_diagnostic ? (
            <>
              <CheckBadge status={item.latest_diagnostic.overall_status} />{' '}
              {formatTime(item.latest_diagnostic.started_at)}
            </>
          ) : (
            'never run'
          )}
        </span>
        <a href={pageHref('diagnostics', { integration: item.integration_id })}>Run diagnostics →</a>
      </footer>
    </article>
  )
}

export default IntegrationHealthCard
