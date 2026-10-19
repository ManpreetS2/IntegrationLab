import assert from 'node:assert/strict'
import test from 'node:test'

import { popPreviousCursor, pushNextCursor } from './telemetryPager.ts'

test('previous moves back exactly one page', () => {
  let cursor: string | undefined = undefined
  let stack: (string | undefined)[] = []

  stack = pushNextCursor(stack, cursor)
  cursor = 'page2'
  stack = pushNextCursor(stack, cursor)
  cursor = 'page3'

  const back = popPreviousCursor(stack)
  stack = back.previousCursors
  cursor = back.cursor

  assert.equal(cursor, 'page2')
  assert.deepEqual(stack, [undefined])
})

test('next pushes the current cursor before advancing', () => {
  const stack = pushNextCursor([], undefined)
  assert.deepEqual(stack, [undefined])
})
