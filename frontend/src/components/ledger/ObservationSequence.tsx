import { useState } from 'react'
import type { SequenceMark } from '../../ledger/sequence'
import { useScrollEdges } from './useScrollEdges'

function ObservationSequence({
  marks,
  onSelect,
}: {
  marks: SequenceMark[]
  onSelect?: (id: string) => void
}) {
  const [node, setNode] = useState<HTMLDivElement | null>(null)
  const edges = useScrollEdges(node, marks.length)
  const reduceMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const behavior = reduceMotion ? 'auto' : 'smooth'

  if (marks.length === 0) {
    return <p className="lg-empty">No observations in this window.</p>
  }

  function scrollBy(distance: number) {
    node?.scrollBy({ left: distance, behavior })
  }

  return (
    <div className={`lg-seq${edges.left ? ' can-left' : ''}${edges.right ? ' can-right' : ''}`}>
      <div className="lg-seq-bar">
        <p className="lg-section-label" style={{ margin: 0 }}>
          Sequence
        </p>
        {edges.left || edges.right ? (
          <p className="lg-seq-hint">Scroll horizontally</p>
        ) : null}
        <div className="lg-seq-nav">
          <button type="button" aria-label="Scroll sequence backward" disabled={!edges.left} onClick={() => scrollBy(-180)}>
            ‹
          </button>
          <button type="button" aria-label="Scroll sequence forward" disabled={!edges.right} onClick={() => scrollBy(180)}>
            ›
          </button>
        </div>
      </div>
      <div
        ref={setNode}
        className="lg-seq-scroller"
        tabIndex={0}
        role="list"
        aria-label="Observation sequence, oldest to newest"
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight') {
            event.preventDefault()
            scrollBy(180)
          }
          if (event.key === 'ArrowLeft') {
            event.preventDefault()
            scrollBy(-180)
          }
        }}
      >
        {marks.map((mark) => {
          const className = `lg-seq-cell${mark.dimmed ? ' is-dimmed' : ''}${mark.selected ? ' is-selected' : ''}`
          const body = (
            <>
              <span className={`lg-lamp ${mark.tone}`} aria-hidden="true" />
              <span className="lg-seq-title">{mark.title}</span>
              <span className="lg-seq-detail">{mark.detail}</span>
            </>
          )
          if (!onSelect) {
            return (
              <div key={mark.id} className={className} role="listitem" aria-current={mark.selected ? 'true' : undefined}>
                {body}
              </div>
            )
          }
          return (
            <button
              key={mark.id}
              type="button"
              className={className}
              role="listitem"
              aria-current={mark.selected ? 'true' : undefined}
              aria-pressed={mark.selected}
              onClick={() => onSelect(mark.id)}
            >
              {body}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default ObservationSequence
