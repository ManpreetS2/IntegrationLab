import { useEffect, useState } from 'react'
import { FIXTURE } from './fixtures'
import './preview.css'

type Concept = 'pearl' | 'graphite'

const NAV = [
  { group: 'Monitor', items: ['Overview', 'Integrations'] },
  { group: 'Investigate', items: ['Requests', 'Webhooks', 'Failures'] },
  { group: 'Resolve', items: ['Diagnostics', 'Support Cases', 'Audit'] },
]

function NavGlyph({ name }: { name: string }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: '0 0 16 16',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.4,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  if (name === 'Overview') {
    return (
      <svg {...common}>
        <rect x="2" y="2" width="5" height="5" rx="1.2" />
        <rect x="9" y="2" width="5" height="5" rx="1.2" />
        <rect x="2" y="9" width="5" height="5" rx="1.2" />
        <rect x="9" y="9" width="5" height="5" rx="1.2" />
      </svg>
    )
  }
  if (name === 'Integrations') {
    return (
      <svg {...common}>
        <circle cx="5" cy="8" r="2.2" />
        <circle cx="11" cy="8" r="2.2" />
        <path d="M7.2 8h1.6" />
      </svg>
    )
  }
  if (name === 'Requests') {
    return (
      <svg {...common}>
        <path d="M3 4.5h10M3 8h10M3 11.5h6" />
      </svg>
    )
  }
  if (name === 'Webhooks') {
    return (
      <svg {...common}>
        <path d="M3.5 6.5h6.2a2.2 2.2 0 1 1 0 4.4H7" />
        <path d="M8.2 9.2 6 11.4l2.2 2.2" />
      </svg>
    )
  }
  if (name === 'Failures') {
    return (
      <svg {...common}>
        <circle cx="8" cy="8" r="5.2" />
        <path d="M8 5.2v3.2" />
        <path d="M8 10.6h.01" />
      </svg>
    )
  }
  if (name === 'Diagnostics') {
    return (
      <svg {...common}>
        <path d="M2.5 8.5h2l1.4-3 2.2 6 1.5-3H13.5" />
      </svg>
    )
  }
  if (name === 'Support Cases') {
    return (
      <svg {...common}>
        <path d="M3 4.5h10v7.2H6.2L3 13.5z" />
      </svg>
    )
  }
  return (
    <svg {...common}>
      <circle cx="8" cy="8" r="5.2" />
      <path d="M8 5.4v2.8l1.8 1.2" />
    </svg>
  )
}

function parseConcept(hash: string): Concept {
  const query = hash.split('?')[1] ?? ''
  return new URLSearchParams(query).get('concept') === 'graphite' ? 'graphite' : 'pearl'
}

function showChrome(hash: string): boolean {
  const query = hash.split('?')[1] ?? ''
  return new URLSearchParams(query).get('chrome') !== '0'
}

export function isDesignPreviewHash(hash = window.location.hash): boolean {
  return hash.replace(/^#\/?/, '').startsWith('design-preview')
}

function Mark({ provider }: { provider: string }) {
  const letter = provider.slice(0, 1)
  return (
    <span className={`pv-mark pv-mark-${provider.toLowerCase()}`} aria-hidden="true">
      {letter}
    </span>
  )
}

function DesignPreview() {
  const [hash, setHash] = useState(() => window.location.hash)
  const [openId, setOpenId] = useState('st')
  const [navOpen, setNavOpen] = useState(false)
  const [refreshed, setRefreshed] = useState(false)
  const concept = parseConcept(hash)
  const chrome = showChrome(hash)

  useEffect(() => {
    const onHash = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    setNavOpen(false)
  }, [concept])

  function go(next: Concept) {
    const chromeQuery = chrome ? '' : '&chrome=0'
    window.location.hash = `/design-preview?concept=${next}${chromeQuery}`
  }

  return (
    <div className={`pv pv-${concept}`} data-concept={concept}>
      {chrome ? (
        <div className="pv-chrome" role="note">
          <span>Design preview · fixtures only · not the product</span>
          <span className="pv-chrome-actions">
            <button type="button" className={concept === 'pearl' ? 'is-on' : ''} onClick={() => go('pearl')}>
              Frosted Pearl
            </button>
            <button type="button" className={concept === 'graphite' ? 'is-on' : ''} onClick={() => go('graphite')}>
              Graphite Glass
            </button>
          </span>
        </div>
      ) : null}

      <div className="pv-app">
        <aside className="pv-side" aria-label="Primary">
          <div className="pv-brand">
            <span className="pv-logo" aria-hidden="true" />
            <div>
              <strong>IntegrationLab</strong>
              <small>Reliability</small>
            </div>
          </div>
          <nav>
            {NAV.map((group) => (
              <div key={group.group} className="pv-group">
                <p>{group.group}</p>
                <ul>
                  {group.items.map((item) => (
                    <li key={item}>
                      <a href="#/design-preview" aria-current={item === 'Overview' ? 'page' : undefined}>
                        <NavGlyph name={item} />
                        {item}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </aside>

        {navOpen ? (
          <button type="button" className="pv-backdrop" aria-label="Close navigation" onClick={() => setNavOpen(false)} />
        ) : null}
        <div className={navOpen ? 'pv-drawer is-open' : 'pv-drawer'} hidden={!navOpen}>
          <button type="button" className="pv-icon" aria-label="Close menu" onClick={() => setNavOpen(false)}>
            Close
          </button>
          <nav aria-label="Sections">
            {NAV.flatMap((group) => group.items).map((item) => (
              <a key={item} href="#/design-preview" aria-current={item === 'Overview' ? 'page' : undefined}>
                {item}
              </a>
            ))}
          </nav>
        </div>

        <div className="pv-main">
          <header className="pv-toolbar">
            <button type="button" className="pv-icon pv-menu" aria-label="Open navigation" onClick={() => setNavOpen(true)}>
              Menu
            </button>
            <h1>Overview</h1>
            <div className="pv-toolbar-end">
              <span className="pv-db" role="status">
                Database reachable
              </span>
              <button type="button" className="pv-btn pv-btn-quiet" onClick={() => setRefreshed(true)}>
                {refreshed ? 'Updated' : 'Refresh'}
              </button>
            </div>
          </header>

          <div className="pv-content">
            <p className="pv-kicker">Fixture</p>
            <h2>{FIXTURE.summary.split('.')[0]}.</h2>
            <p className="pv-lead">{FIXTURE.summary.slice(FIXTURE.summary.indexOf('.') + 1).trim()}</p>
            <p className="pv-note">{FIXTURE.support}</p>
            <p className="pv-note pv-fixture">{FIXTURE.notice}</p>

            <section className="pv-metrics" aria-label="Health counts">
              {FIXTURE.metrics.map((metric) => (
                <div
                  key={metric.label}
                  className={metric.value === '0' ? 'pv-metric' : `pv-metric tone-${metric.tone}`}
                >
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </section>

            <section className="pv-sheet">
              <header>
                <h3>Needs attention</h3>
              </header>
              <div className="pv-row pv-row-focus">
                <Mark provider={FIXTURE.attention.provider} />
                <div className="pv-row-copy">
                  <strong>{FIXTURE.attention.name}</strong>
                  <span>{FIXTURE.attention.line}</span>
                </div>
                <span className="pv-pill pv-pill-warn">{FIXTURE.attention.state}</span>
                <button
                  type="button"
                  className="pv-btn pv-btn-primary"
                  onClick={() => {
                    setOpenId('st')
                    document.getElementById('pv-integration-st')?.scrollIntoView({ block: 'nearest' })
                  }}
                >
                  {FIXTURE.attention.action}
                </button>
              </div>
            </section>

            <section className="pv-sheet">
              <header>
                <h3>Integrations</h3>
              </header>
              <ul className="pv-list">
                {FIXTURE.integrations.map((item) => {
                  const open = openId === item.id
                  return (
                    <li key={item.id} id={`pv-integration-${item.id}`}>
                      <button
                        type="button"
                        className={open ? 'pv-row is-open' : 'pv-row'}
                        aria-expanded={open}
                        onClick={() => setOpenId(open ? '' : item.id)}
                      >
                        <Mark provider={item.provider} />
                        <div className="pv-row-copy">
                          <strong>{item.name}</strong>
                          <span>{item.provider}</span>
                        </div>
                        <span className={`pv-pill pv-pill-${item.tone}`}>{item.state}</span>
                      </button>
                      {open ? <p className="pv-detail">{item.detail}</p> : null}
                    </li>
                  )
                })}
              </ul>
            </section>

            <section className="pv-sheet">
              <header>
                <h3>Recent activity</h3>
              </header>
              <ul className="pv-list">
                {FIXTURE.activity.map((item) => (
                  <li key={item.title} className="pv-activity">
                    <span className="pv-kind">{item.kind}</span>
                    <div>
                      <strong>{item.title}</strong>
                      <span>{item.meta}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DesignPreview
