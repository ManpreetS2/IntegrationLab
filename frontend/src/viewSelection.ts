/** Records loaded for one owner. A mismatch means "not ready", not "empty". */
export interface ScopedLoad<T> {
  ownerId: string
  records: T[]
}

/**
 * Return records only when they were loaded for the current selection.
 * Null means the previous selection's data must stay hidden.
 */
export function recordsForSelection<T>(
  selectedId: string | null | undefined,
  loaded: ScopedLoad<T> | null | undefined,
): T[] | null {
  if (!selectedId || !loaded || loaded.ownerId !== selectedId) return null
  return loaded.records
}

/** A single record is visible only when its integration id is the selected one. */
export function recordForSelection<T extends { integration_id: string }>(
  selectedId: string | null | undefined,
  record: T | null | undefined,
): T | undefined {
  if (!selectedId || !record || record.integration_id !== selectedId) return undefined
  return record
}
