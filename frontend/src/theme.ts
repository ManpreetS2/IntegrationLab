export type Appearance = 'system' | 'light' | 'dark'
export type Theme = 'light' | 'dark'

export const APPEARANCE_KEY = 'integrationlab.appearance'

export function readAppearance(storage: Pick<Storage, 'getItem'> | null): Appearance {
  const value = storage?.getItem(APPEARANCE_KEY)
  if (value === 'light' || value === 'dark' || value === 'system') return value
  return 'system'
}

export function resolveTheme(appearance: Appearance, prefersDark: boolean): Theme {
  if (appearance === 'system') return prefersDark ? 'dark' : 'light'
  return appearance
}

export function applyAppearance(appearance: Appearance, prefersDark: boolean): Theme {
  const theme = resolveTheme(appearance, prefersDark)
  const root = document.documentElement
  root.dataset.theme = theme
  root.dataset.appearance = appearance
  root.style.colorScheme = theme
  return theme
}
