export interface FocusCandidate {
  id: string
  visible: boolean
}

/**
 * Choose the option to focus after arrow-key navigation.
 * Callers pass only the options that belong to the list which received the key.
 * A duplicate id in another list, including the same webhook event in the
 * delivery list and the failed queue, is not a candidate.
 */
export function focusableOptionInList<T extends FocusCandidate>(options: readonly T[], id: string): T | undefined {
  return options.find((option) => option.id === id && option.visible)
}
