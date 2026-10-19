/** Parse FastAPI error bodies for operator-facing messages. */

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function explainApiError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : fallback
  }
  const raw = error.message.trim()
  if (!raw) return fallback
  try {
    const body = JSON.parse(raw) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      const first = body.detail[0]
      if (first && typeof first === 'object' && first !== null && 'msg' in first) {
        const msg = (first as { msg?: unknown }).msg
        if (typeof msg === 'string') return msg
      }
    }
    if (body.detail && typeof body.detail === 'object' && 'message' in body.detail) {
      const message = (body.detail as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  } catch {
    return raw
  }
  return raw
}
