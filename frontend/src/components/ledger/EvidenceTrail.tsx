import type { ReactNode } from 'react'
import type { TrailStation } from '../../ledger/trail'

function EvidenceTrail({
  title,
  stations,
  action,
}: {
  title: string
  stations: TrailStation[]
  action?: ReactNode
}) {
  return (
    <aside className="lg-trail" aria-label="Evidence trail">
      <h2 className="lg-trail-title">{title}</h2>
      {stations.map((station) => (
        <div key={station.label} className="lg-station">
          <p className="lg-station-label">{station.label}</p>
          <p>{station.text}</p>
        </div>
      ))}
      {action}
    </aside>
  )
}

export default EvidenceTrail
