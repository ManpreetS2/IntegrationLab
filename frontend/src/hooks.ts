import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { ApiError } from './api'

export type Page = 'overview' | 'integrations' | 'requests' | 'webhooks' | 'failures' | 'diagnostics'

export const PAGES: { id: Page; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'requests', label: 'Requests' },
  { id: 'webhooks', label: 'Webhooks' },
  { id: 'failures', label: 'Failures' },
  { id: 'diagnostics', label: 'Diagnostics' },
]

const PAGE_IDS = new Set<string>(PAGES.map((page) => page.id))

export interface HashRoute {
  page: Page
  params: URLSearchParams
}

function parseHash(hash: string): HashRoute {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?')
  const page = PAGE_IDS.has(path) ? (path as Page) : 'overview'
  return { page, params: new URLSearchParams(query) }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

/** Hash navigation (`#/overview`, `#/diagnostics?integration=<id>`) without a router dependency. */
export function useHashRoute(): HashRoute {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  return useMemo(() => parseHash(hash), [hash])
}

export function pageHref(page: Page, params?: Record<string, string>): string {
  const query = params ? new URLSearchParams(params).toString() : ''
  return `#/${page}${query ? `?${query}` : ''}`
}

export function navigate(page: Page, params?: Record<string, string>): void {
  window.location.hash = pageHref(page, params).slice(1)
}

export function errorMessage(err: unknown, fallback = 'Request failed.'): string {
  if (err instanceof ApiError && err.status === 503) return 'Database unavailable.'
  if (err instanceof TypeError) return 'Backend unreachable. Is the API running?'
  return err instanceof Error ? err.message : fallback
}

interface ResourceState<T> {
  load: (() => Promise<T>) | null
  nonce: number
  data: T | undefined
  error: unknown
}

export interface Resource<T> {
  data: T | undefined
  error: unknown
  loading: boolean
  reload: () => void
}

/**
 * Load one independent section. Pass a stable loader (module function or useCallback);
 * changing the loader or calling reload() refetches. Previous data stays visible while
 * refreshing, so sections do not flash empty. A null loader means "nothing to load".
 */
export function useResource<T>(load: (() => Promise<T>) | null): Resource<T> {
  const [nonce, setNonce] = useState(0)
  const [state, setState] = useState<ResourceState<T>>({
    load: null,
    nonce: -1,
    data: undefined,
    error: null,
  })

  useEffect(() => {
    if (!load) return
    let cancelled = false
    load().then(
      (data) => {
        if (!cancelled) setState({ load, nonce, data, error: null })
      },
      (error: unknown) => {
        if (!cancelled) setState((prev) => ({ load, nonce, data: prev.data, error }))
      },
    )
    return () => {
      cancelled = true
    }
  }, [load, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  const current = state.load === load && state.nonce === nonce
  return {
    data: load ? state.data : undefined,
    error: current ? state.error : null,
    loading: load !== null && !current,
    reload,
  }
}
