/**
 * Stripe display formatting for stored minor-unit amounts.
 * Zero-decimal currencies (e.g. JPY) must not be divided by 100.
 * @see https://docs.stripe.com/currencies#zero-decimal
 */
const ZERO_DECIMAL_CURRENCIES = new Set([
  'bif',
  'clp',
  'djf',
  'gnf',
  'jpy',
  'kmf',
  'krw',
  'mga',
  'pyg',
  'rwf',
  'ugx',
  'vnd',
  'vuv',
  'xaf',
  'xof',
  'xpf',
])

export function formatStripeAmount(amount: number | null, currency: string | null): string {
  if (amount === null || currency === null) return '—'
  const code = currency.trim().toLowerCase()
  if (!code) return '—'
  const label = code.toUpperCase()
  if (ZERO_DECIMAL_CURRENCIES.has(code)) {
    return `${amount} ${label}`
  }
  return `${(amount / 100).toFixed(2)} ${label}`
}
