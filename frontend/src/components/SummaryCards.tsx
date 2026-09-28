import type { Integration } from '../types'

interface SummaryCardsProps {
  integrations: Integration[]
}

function SummaryCards({ integrations }: SummaryCardsProps) {
  const total = integrations.length
  const connected = integrations.filter((item) => item.status === 'connected').length
  const needsSetup = integrations.filter(
    (item) => item.status === 'needs_setup' || item.status === 'not_connected',
  ).length

  return (
    <section className="summary-grid" aria-label="Integration summary">
      <article className="summary-card">
        <p className="summary-label">Total integrations</p>
        <p className="summary-value">{total}</p>
      </article>
      <article className="summary-card">
        <p className="summary-label">Connected</p>
        <p className="summary-value">{connected}</p>
      </article>
      <article className="summary-card">
        <p className="summary-label">Needs setup</p>
        <p className="summary-value">{needsSetup}</p>
      </article>
    </section>
  )
}

export default SummaryCards
