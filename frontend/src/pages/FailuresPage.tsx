import { useCallback, useState } from 'react'
import { listReliabilityFailures } from '../api'
import FailureLabPanel from '../components/FailureLabPanel'
import FailuresTable from '../components/FailuresTable'
import SectionStatus from '../components/SectionStatus'
import { useResource } from '../hooks'
import type { FailureSource, Integration, IntegrationProvider } from '../types'

type FailureFilter = 'all' | 'github' | 'stripe' | 'failure_lab' | 'diagnostic'

const FILTERS: { id: FailureFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'github', label: 'GitHub API' },
  { id: 'stripe', label: 'Stripe processing' },
  { id: 'diagnostic', label: 'Diagnostics' },
  { id: 'failure_lab', label: 'Failure Lab (simulation)' },
]

const FILTER_PARAMS: Record<FailureFilter, { provider?: IntegrationProvider; source?: FailureSource }> = {
  all: {},
  github: { provider: 'github', source: 'provider_request' },
  stripe: { provider: 'stripe', source: 'webhook_processing' },
  diagnostic: { source: 'diagnostic' },
  failure_lab: { source: 'failure_lab' },
}

interface FailuresPageProps {
  integrations: Integration[]
  onIntegrationsChanged: () => void
}

function FailuresPage({ integrations, onIntegrationsChanged }: FailuresPageProps) {
  const [filter, setFilter] = useState<FailureFilter>('all')
  const [includeSimulated, setIncludeSimulated] = useState(false)
  const [windowHours, setWindowHours] = useState(24)

  const loadFailures = useCallback(
    () =>
      listReliabilityFailures({
        ...FILTER_PARAMS[filter],
        include_simulated: filter === 'all' ? includeSimulated : undefined,
        window_hours: windowHours,
        limit: 100,
      }),
    [filter, includeSimulated, windowHours],
  )
  const failures = useResource(loadFailures)
  const reloadFailures = failures.reload

  const handleLabCompleted = useCallback(() => {
    reloadFailures()
    onIntegrationsChanged()
  }, [reloadFailures, onIntegrationsChanged])

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <h2>Failures</h2>
          <button type="button" className="secondary-button" onClick={failures.reload}>
            Refresh
          </button>
        </div>
        <div className="segmented" role="tablist" aria-label="Failure source">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={filter === item.id}
              className={filter === item.id ? 'segment segment-active' : 'segment'}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="webhook-toolbar filter-row">
          <label>
            Window
            <select value={windowHours} onChange={(e) => setWindowHours(Number(e.target.value))}>
              <option value={24}>Last 24h</option>
              <option value={168}>Last 7 days</option>
            </select>
          </label>
          {filter === 'all' ? (
            <label className="inline-check">
              <input
                type="checkbox"
                checked={includeSimulated}
                onChange={(e) => setIncludeSimulated(e.target.checked)}
              />
              Include simulations
            </label>
          ) : null}
        </div>
        <SectionStatus
          loading={failures.loading}
          error={failures.error}
          hasData={Boolean(failures.data)}
          onRetry={failures.reload}
          loadingText="Loading failures…"
        />
        {failures.data ? (
          <FailuresTable
            items={failures.data}
            emptyText={
              filter === 'failure_lab'
                ? 'No Failure Lab simulations in this window.'
                : 'No failures match these filters.'
            }
          />
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Failure Lab</h2>
          <span className="source-badge source-simulated">Simulation</span>
        </div>
        <p className="muted">
          Sandboxed scenarios. Results are labeled simulated, excluded from health and real metrics, and
          never change a real connection.
        </p>
        <FailureLabPanel integrations={integrations} onCompleted={handleLabCompleted} />
      </section>
    </>
  )
}

export default FailuresPage
