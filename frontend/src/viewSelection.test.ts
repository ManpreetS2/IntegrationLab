import assert from 'node:assert/strict'
import { test } from 'node:test'
import { recordForSelection, recordsForSelection } from './viewSelection.ts'

test('credential metadata from another application stays hidden', () => {
  const loaded = {
    ownerId: 'app-a',
    records: [{ key_prefix: 'ilk_v1_aaaaaaaaaaaa' }],
  }
  assert.equal(recordsForSelection('app-b', loaded), null)
  assert.deepEqual(recordsForSelection('app-a', loaded), loaded.records)
})

test('a loaded empty credential list is empty, not the previous list', () => {
  assert.deepEqual(recordsForSelection('app-b', { ownerId: 'app-b', records: [] }), [])
  assert.equal(recordsForSelection(null, { ownerId: 'app-a', records: [{ key_prefix: 'ilk_v1_x' }] }), null)
})

test('telemetry for another integration is not shown while the next load is pending', () => {
  const previous = { integration_id: 'app-a', health: 'degraded' }
  assert.equal(recordForSelection('app-b', previous), undefined)
  assert.equal(recordForSelection('app-a', previous), previous)
  assert.equal(recordForSelection('app-a', undefined), undefined)
})
