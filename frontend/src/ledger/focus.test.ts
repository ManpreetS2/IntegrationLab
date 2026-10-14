import assert from 'node:assert/strict'
import test from 'node:test'
import { focusableOptionInList } from './focus.ts'

test('arrow-key focus stays in the list that received the key when an id is shared', () => {
  const delivery = [
    { id: 'evt-shared', visible: true, list: 'deliveries' },
    { id: 'evt-other', visible: true, list: 'deliveries' },
  ]
  const failed = [
    { id: 'evt-shared', visible: true, list: 'failed' },
    { id: 'evt-older', visible: true, list: 'failed' },
  ]
  const hiddenCard = { id: 'evt-older', visible: false, list: 'failed' }

  assert.equal(focusableOptionInList(delivery, 'evt-shared')?.list, 'deliveries')
  assert.equal(focusableOptionInList(failed, 'evt-shared')?.list, 'failed')
  assert.equal(focusableOptionInList([hiddenCard, ...failed], 'evt-older')?.list, 'failed')
  assert.equal(focusableOptionInList([hiddenCard, ...failed], 'evt-older')?.visible, true)
  assert.equal(focusableOptionInList(delivery, 'evt-shared'), delivery[0])
  assert.notEqual(focusableOptionInList(failed, 'evt-shared'), delivery[0])
})
