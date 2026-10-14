import assert from 'node:assert/strict'
import test from 'node:test'
import { identifierParts } from './identifier.ts'

test('audit identifiers break only on underscores', () => {
  const parts = identifierParts('ingestion_credential_created')
  assert.deepEqual(parts, ['ingestion', 'credential', 'created'])
  for (const part of parts) {
    assert.equal(part.includes('_'), false)
    assert.equal(part.includes('\u200b'), false)
    assert.ok(part.length > 1)
  }
  assert.equal(identifierParts('support_case_created').join('_'), 'support_case_created')
})
