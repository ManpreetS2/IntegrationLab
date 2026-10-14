import { useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { HEALTH_LABELS } from '../../format'
import { healthTone } from '../../ledger/copy'
import type { HealthState } from '../../types'
import { useScrollEdges } from './useScrollEdges'

export function HealthWord({ state }: { state: HealthState }) {
  const tone = healthTone(state)
  return (
    <span className={tone === 'hollow' ? 'lg-health lg-health-quiet' : `lg-health lg-health-${tone}`}>
      <span className={`lg-lamp ${tone}`} aria-hidden="true" />
      {HEALTH_LABELS[state]}
    </span>
  )
}

export interface LedgerRow {
  id: string
  cells: ReactNode[]
  title: string
  meta: ReactNode
  detail?: ReactNode
}

function focusOption(id: string) {
  window.setTimeout(() => {
    const matches = Array.from(document.querySelectorAll<HTMLElement>('[data-lg-option]'))
    matches.find((element) => element.dataset.lgId === id && element.getClientRects().length > 0)?.focus()
  }, 0)
}

function onOptionKey(
  event: KeyboardEvent<HTMLElement>,
  onSelect: (id: string) => void,
  onOpen?: (id: string) => void,
) {
  if (event.key === 'Enter') {
    event.preventDefault()
    const id = event.currentTarget.dataset.lgId
    if (id) onOpen?.(id)
    return
  }
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  event.preventDefault()
  const group = event.currentTarget.closest('[data-lg-list]')
  const options = Array.from(group?.querySelectorAll<HTMLElement>('[data-lg-option]') ?? []).filter(
    (element) => element.getClientRects().length > 0,
  )
  const index = options.indexOf(event.currentTarget)
  const next = options[index + (event.key === 'ArrowDown' ? 1 : -1)]
  const id = next?.dataset.lgId
  if (!id) return
  onSelect(id)
  focusOption(id)
}

function LedgerList({
  label,
  columns,
  rows,
  selectedId,
  onSelect,
  onOpen,
  emptyText,
}: {
  label: string
  columns: string[]
  rows: LedgerRow[]
  selectedId: string | null
  onSelect: (id: string) => void
  onOpen?: (id: string) => void
  emptyText: string
}) {
  if (rows.length === 0) return <p className="lg-empty">{emptyText}</p>

  return (
    <div data-lg-list>
      <div className="lg-table-wrap">
        <table className="lg-table">
          <caption className="lg-kicker">{label}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const selected = row.id === selectedId
              return (
                <tr
                  key={row.id}
                  data-lg-option
                  data-lg-id={row.id}
                  tabIndex={selected ? 0 : -1}
                  aria-selected={selected}
                  className={selected ? 'is-selected' : undefined}
                  onClick={() => onSelect(row.id)}
                  onKeyDown={(event) => onOptionKey(event, onSelect, onOpen)}
                >
                  {row.cells.map((cell, index) => (
                    <td key={`${row.id}-${index}`}>{cell}</td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="lg-cards" role="listbox" aria-label={label}>
        {rows.map((row) => {
          const selected = row.id === selectedId
          return (
            <div
              key={row.id}
              data-lg-option
              data-lg-id={row.id}
              role="option"
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              className={selected ? 'lg-card is-selected' : 'lg-card'}
              onClick={() => onSelect(row.id)}
              onKeyDown={(event) => onOptionKey(event, onSelect, onOpen)}
            >
              <strong>{row.title}</strong>
              <span>{row.meta}</span>
              {row.detail ? <span className="lg-muted">{row.detail}</span> : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default LedgerList

export function LedgerFilters({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: { id: string; label: string }[]
  onChange: (id: string) => void
}) {
  const [node, setNode] = useState<HTMLDivElement | null>(null)
  const edges = useScrollEdges(node, options.map((option) => option.id).join('|'))
  return (
    <div className={`lg-filter-wrap${edges.right ? ' can-right' : ''}`}>
    <div ref={setNode} className="segmented lg-filters" role="tablist" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="tab"
          aria-selected={value === option.id}
          className={value === option.id ? 'segment segment-active' : 'segment'}
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
    {edges.right ? (
      <span className="lg-scroll-cue" aria-hidden="true">
        ›
      </span>
    ) : null}
    </div>
  )
}

export function RuleList({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="lg-rules">
      {rows.map(([label, text]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{text}</dd>
        </div>
      ))}
    </dl>
  )
}
