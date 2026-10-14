import type { ReactNode } from 'react'
import type { TrailStation } from '../../ledger/trail'
import IdentifierText from './IdentifierText'

function EvidenceTrail({
  title,
  stations,
  action,
  identifier = false,
}: {
  title: string
  stations: TrailStation[]
  action?: ReactNode
  identifier?: boolean
}) {
  return (
    <aside className="lg-trail" aria-label="Evidence trail">
      <h2 className={identifier ? 'lg-trail-title lg-id' : 'lg-trail-title'}>
        {identifier ? <IdentifierText value={title} /> : title}
      </h2>
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
