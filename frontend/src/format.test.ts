import assert from 'node:assert/strict'
import test from 'node:test'
import { formatErrorRate, formatP95 } from './format.ts'

test('a missing error rate is unavailable', () => {
  assert.equal(formatErrorRate(null), 'Unavailable')
  assert.equal(formatErrorRate(undefined), 'Unavailable')
})

test('a real zero error rate stays zero', () => {
  assert.equal(formatErrorRate(0), '0%')
})

test('error rate is a percentage of the ratio', () => {
  assert.equal(formatErrorRate(0.6), '60%')
})

test('p95 stays unavailable below 20 samples', () => {
  assert.equal(formatP95(80, 5), 'Unavailable')
  assert.equal(formatP95(null, 20), 'Unavailable')
  assert.equal(formatP95(80, 20), '80 ms')
})
