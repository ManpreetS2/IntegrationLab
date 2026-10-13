import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { API_URL } from '../api'
import { NAV_GROUPS, PAGE_META, pageHref, type Page } from '../hooks'
import AppearanceControl from './AppearanceControl'
import { AppMark, MenuIcon, NavIcon } from './NavIcons'
import PageHeader from './PageHeader'

interface AppShellProps {
  page: Page
  connectivity: ReactNode
  children: ReactNode
}

function AppShell({ page, connectivity, children }: AppShellProps) {
  const [navOpen, setNavOpen] = useState(false)
  const drawerId = useId()
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const meta = PAGE_META[page]

  useEffect(() => {
    if (!navOpen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeBtnRef.current?.focus()

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey)
    }
  }, [navOpen])

  const nav = (
    <>
      <div className="sidebar-brand">
        <AppMark />
        <div>
          <p className="brand-name">IntegrationLab</p>
          <p className="brand-tag">Reliability console</p>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Console sections">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="nav-group">
            <p className="nav-group-label">{group.label}</p>
            <ul className="nav-list">
              {group.pages.map((id) => {
                const active = page === id
                return (
                  <li key={id}>
                    <a
                      href={pageHref(id)}
                      className={active ? 'nav-link nav-link-active' : 'nav-link'}
                      aria-current={active ? 'page' : undefined}
                      onClick={() => setNavOpen(false)}
                    >
                      <NavIcon page={id} />
                      <span>{PAGE_META[id].label}</span>
                    </a>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <footer className="sidebar-footer">
        <p className="muted small-text">Single-operator · self-hosted</p>
        <p className="mono-meta" title={API_URL || 'same origin'}>
          API · {API_URL || 'same origin'}
        </p>
      </footer>
    </>
  )

  return (
    <div className="app-frame">
      <aside className="app-sidebar" aria-label="Primary">
        {nav}
      </aside>

      {navOpen ? (
        <button
          type="button"
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      ) : null}

      <div
        id={drawerId}
        className={navOpen ? 'mobile-drawer mobile-drawer-open' : 'mobile-drawer'}
        role="dialog"
        aria-modal={navOpen ? true : undefined}
        aria-label="Navigation"
        hidden={!navOpen}
        aria-hidden={!navOpen}
      >
        <div className="mobile-drawer-top">
          <button
            ref={closeBtnRef}
            type="button"
            className="icon-button"
            aria-label="Close menu"
            onClick={() => setNavOpen(false)}
          >
            <MenuIcon open />
          </button>
        </div>
        {nav}
      </div>

      <div className="app-column">
        <header className="app-topbar">
          <button
            type="button"
            className="icon-button menu-toggle"
            aria-label={navOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={navOpen}
            aria-controls={drawerId}
            onClick={() => setNavOpen((open) => !open)}
          >
            <MenuIcon open={navOpen} />
          </button>
          <div className="topbar-title-block">
            <PageHeader title={meta.title} description={meta.description} />
          </div>
          <div className="topbar-meta">
            <AppearanceControl />
            {connectivity}
          </div>
        </header>
        <main className="app-main">{children}</main>
      </div>
    </div>
  )
}

export default AppShell
