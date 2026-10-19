/** Cursor stack for telemetry event paging (one page back per Previous click). */

export type TelemetryCursor = string | undefined

export function popPreviousCursor(previousCursors: TelemetryCursor[]): {
  previousCursors: TelemetryCursor[]
  cursor: TelemetryCursor
} {
  const cursor = previousCursors.at(-1)
  return { previousCursors: previousCursors.slice(0, -1), cursor }
}

export function pushNextCursor(
  previousCursors: TelemetryCursor[],
  current: TelemetryCursor,
): TelemetryCursor[] {
  return [...previousCursors, current]
}
