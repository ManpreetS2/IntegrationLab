const OPERATOR_KEY_STORAGE = 'integrationlab.operatorApiKey'

export function getOperatorApiKey(): string | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage.getItem(OPERATOR_KEY_STORAGE)
}

export function setOperatorApiKey(value: string): void {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(OPERATOR_KEY_STORAGE, value)
}

export function clearOperatorApiKey(): void {
  if (typeof window === 'undefined') return
  window.sessionStorage.removeItem(OPERATOR_KEY_STORAGE)
}
