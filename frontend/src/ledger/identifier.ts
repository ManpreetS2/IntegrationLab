/** Split a technical identifier on underscores so a line can break only between words. */
export function identifierParts(value: string): string[] {
  return value.split('_')
}
