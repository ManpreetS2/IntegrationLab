import type { ReactNode } from 'react'
import type { Page } from '../hooks'

const size = 18

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

export function NavIcon({ page }: { page: Page }) {
  switch (page) {
    case 'overview':
      return (
        <Icon>
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </Icon>
      )
    case 'integrations':
      return (
        <Icon>
          <path d="M10 13a5 5 0 0 0 7.54.54l1.92-1.92a5 5 0 0 0-7.07-7.07L11 6" />
          <path d="M14 11a5 5 0 0 0-7.54-.54L4.54 12.4a5 5 0 0 0 7.07 7.07L13 18" />
        </Icon>
      )
    case 'telemetry':
      return (
        <Icon>
          <path d="M4 16h3l2-6 2 8 2-5h7" />
        </Icon>
      )
    case 'requests':
      return (
        <Icon>
          <path d="M4 6h16" />
          <path d="M4 12h10" />
          <path d="M4 18h14" />
          <path d="M18 10v8" />
          <path d="M15 15l3 3 3-3" />
        </Icon>
      )
    case 'webhooks':
      return (
        <Icon>
          <path d="M18 16.5a3.5 3.5 0 1 0-3.4-4.4L10 14.5" />
          <path d="M6 7.5a3.5 3.5 0 1 0 3.4 4.4L14 9.5" />
          <circle cx="6" cy="7.5" r="1" fill="currentColor" stroke="none" />
          <circle cx="18" cy="16.5" r="1" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        </Icon>
      )
    case 'failures':
      return (
        <Icon>
          <path d="M12 9v4" />
          <path d="M12 17h.01" />
          <path d="M10.3 4.3 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z" />
        </Icon>
      )
    case 'diagnostics':
      return (
        <Icon>
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z" />
        </Icon>
      )
    case 'support':
      return (
        <Icon>
          <path d="M15 5H9a2 2 0 0 0-2 2v12l5-3 5 3V7a2 2 0 0 0-2-2Z" />
        </Icon>
      )
    case 'audit':
      return (
        <Icon>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6" />
          <path d="M8 13h8" />
          <path d="M8 17h5" />
        </Icon>
      )
  }
}

export function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      {open ? (
        <>
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </>
      ) : (
        <>
          <path d="M4 7h16" />
          <path d="M4 12h16" />
          <path d="M4 17h16" />
        </>
      )}
    </svg>
  )
}

export function AppMark() {
  return (
    <svg
      className="app-mark"
      width={28}
      height={28}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="8" fill="var(--color-accent-soft)" stroke="var(--color-accent)" strokeWidth="1.5" />
      <path
        d="M10 16h4l2-5 3 10 2-5h3"
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
