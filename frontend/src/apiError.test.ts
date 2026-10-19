import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError, explainApiError } from './lib/apiError.ts'
import { errorMessage } from './hooks.ts'

test('errorMessage parses ApiError detail string', () => {
  const err = new ApiError(
    409,
    '{"detail":"Only failed or dismissed events can be retried (status: processed)"}',
  )
  assert.equal(
    errorMessage(err),
    'Only failed or dismissed events can be retried (status: processed)',
  )
  assert.equal(
    explainApiError(err, 'fallback'),
    'Only failed or dismissed events can be retried (status: processed)',
  )
})

test('errorMessage parses FastAPI 422 list detail', () => {
  const err = new ApiError(
    422,
    '{"detail":[{"type":"string_too_short","loc":["body","title"],"msg":"String should have at least 1 character"}]}',
  )
  assert.equal(errorMessage(err), 'String should have at least 1 character')
})

test('errorMessage for integration create failures', () => {
  const err = new ApiError(409, '{"detail":"An integration with this name already exists"}')
  assert.equal(
    errorMessage(err, 'Failed to create integration.'),
    'An integration with this name already exists',
  )
})

test('errorMessage keeps 503 database shortcut', () => {
  const err = new ApiError(503, '{"detail":"Database temporarily unavailable"}')
  assert.equal(errorMessage(err), 'Database unavailable.')
})
