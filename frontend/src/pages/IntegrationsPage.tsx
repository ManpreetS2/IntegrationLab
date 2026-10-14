import { useMemo, useState } from 'react'
import { apiOrigin, getReliabilityOverview } from '../api'
import CreateIntegrationForm from '../components/CreateIntegrationForm'
import EvidenceTrail from '../components/ledger/EvidenceTrail'
import GitHubConnectionPanel from '../components/GitHubConnectionPanel'
import InstrumentedApps from '../components/InstrumentedApps'
import LedgerList from '../components/ledger/LedgerList'
import SectionStatus from '../components/SectionStatus'
import { formatIntegrationStatus, formatProvider } from '../format'
import { pageHref, useResource, type Resource } from '../hooks'
import { integrationFinding } from '../ledger/copy'
import type { TrailStation } from '../ledger/trail'
import type { Environment, Integration, IntegrationProvider } from '../types'

interface IntegrationsPageProps {
  integrations: Resource<Integration[]>
  onCreate: (name: string, provider: IntegrationProvider, environment?: Environment) => Promise<void>
}

function loadOverview() {
  return getReliabilityOverview(24)
}

function connectionStatus(item: Integration): string {
  if (item.provider === 'stripe') return 'Webhook endpoint'
  return formatIntegrationStatus(item.status)
}

function IntegrationsPage({ integrations, onCreate }: IntegrationsPageProps) {
  const items = useMemo(() => integrations.data ?? [], [integrations.data])
  const [pickedId, setPickedId] = useState<string | null>(null)
  const overview = useResource(loadOverview)
  const verification = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const health of overview.data?.integrations ?? []) {
      if (health.webhook_metrics) map.set(health.integration_id, health.webhook_metrics.verification_configured)
    }
    return map
  }, [overview.data])

  const selected =
    items.find((item) => item.id === pickedId) ??
    items.find((item) => item.status === 'not_connected' || item.status === 'needs_setup' || item.status === 'registered') ??
    items[0] ??
    null

  function verificationText(id: string): string {
    const configured = verification.get(id)
    if (configured === undefined) return overview.error ? 'Unavailable' : 'Checking…'
    return configured ? 'Configured' : 'Not configured'
  }

  const stations: TrailStation[] = selected
    ? [
        { label: 'Provider', text: formatProvider(selected.provider) },
        { label: 'Status', text: connectionStatus(selected) },
        { label: 'Environment', text: selected.environment },
        ...(selected.provider === 'stripe'
          ? [{ label: 'Verification', text: verificationText(selected.id) }]
          : []),
        ...(selected.provider === 'instrumented_http'
          ? [{ label: 'Credential', text: 'The secret is shown once. This page keeps only the prefix.' }]
          : []),
      ].slice(0, 5)
    : [{ label: 'Register', text: 'Create a GitHub, Stripe, or instrumented HTTP record.' }]

  const actionHref = selected
    ? selected.provider === 'instrumented_http'
      ? pageHref('telemetry', { integration: selected.id })
      : selected.provider === 'stripe'
        ? pageHref('webhooks')
        : pageHref('diagnostics', { integration: selected.id })
    : null

  return (
    <div className={integrations.loading ? 'lg-busy' : undefined} aria-busy={integrations.loading || undefined}>
      <SectionStatus
        loading={integrations.loading}
        error={integrations.error}
        hasData={Boolean(integrations.data)}
        onRetry={integrations.reload}
        loadingText="Loading integrations…"
      />
      {integrations.data ? (
        <div className="lg-page">
          <div className="lg-main">
            <p className="lg-kicker">Integrations</p>
            <h1 className="lg-finding">{integrationFinding(items)}</h1>
            <p className="lg-note">
              {items.length} registered. GitHub uses OAuth. Stripe uses a webhook endpoint. Instrumented applications
              report their own HTTP calls.
            </p>
            <LedgerList
              label="Integrations"
              columns={['Integration', 'Provider', 'Status', 'Environment']}
              rows={items.map((item) => ({
                id: item.id,
                title: item.name,
                meta: formatProvider(item.provider),
                detail: `${connectionStatus(item)} · ${item.environment}`,
                cells: [
                  <strong key="name">{item.name}</strong>,
                  formatProvider(item.provider),
                  connectionStatus(item),
                  item.environment,
                ],
              }))}
              selectedId={selected?.id ?? null}
              onSelect={setPickedId}
              emptyText="No integrations yet. Register one below."
            />
            {selected?.provider === 'github' ? (
              <section>
                <p className="lg-section-label">GitHub connection</p>
                <GitHubConnectionPanel integration={selected} onStatusChange={integrations.reload} />
              </section>
            ) : null}
            {selected?.provider === 'stripe' ? (
              <section>
                <p className="lg-section-label">Webhook endpoint</p>
                <p className="lg-note">
                  Point Stripe, or <span className="lg-mono">stripe listen --forward-to</span>, at this URL. The signing
                  secret stays in the backend environment.
                </p>
                <p className="lg-mono">{`${apiOrigin()}/webhooks/stripe/${selected.id}`}</p>
                <p className="lg-note">Verification: {verificationText(selected.id)}</p>
              </section>
            ) : null}
            {selected?.provider === 'instrumented_http' ? (
              <InstrumentedApps integrations={[selected]} onChanged={integrations.reload} />
            ) : null}
            <section>
              <p className="lg-section-label">Register</p>
              <CreateIntegrationForm onSubmit={onCreate} disabled={integrations.loading && !integrations.data} />
            </section>
          </div>
          <EvidenceTrail
            title={selected?.name ?? 'Registration'}
            stations={stations}
            action={
              actionHref ? (
                <a className="button-link" href={actionHref}>
                  {selected?.provider === 'instrumented_http'
                    ? 'Open telemetry'
                    : selected?.provider === 'stripe'
                      ? 'Open webhooks'
                      : 'Open diagnostics'}
                </a>
              ) : null
            }
          />
        </div>
      ) : null}
    </div>
  )
}

export default IntegrationsPage
