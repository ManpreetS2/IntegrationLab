/**
 * Node built-in test runner against the shipped formatter (Node 22+ strip-types).
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { formatStripeAmount } from './stripeAmount.ts'

test('USD uses two fractional digits', () => {
  assert.equal(formatStripeAmount(2000, 'usd'), '20.00 USD')
  assert.equal(formatStripeAmount(4200, 'USD'), '42.00 USD')
})

test('JPY is zero-decimal (no /100)', () => {
  assert.equal(formatStripeAmount(500, 'jpy'), '500 JPY')
  assert.equal(formatStripeAmount(1234, 'JPY'), '1234 JPY')
})

test('KRW is zero-decimal', () => {
  assert.equal(formatStripeAmount(1000, 'krw'), '1000 KRW')
})

test('null amount or currency yields em dash', () => {
  assert.equal(formatStripeAmount(null, 'usd'), '—')
  assert.equal(formatStripeAmount(2000, null), '—')
  assert.equal(formatStripeAmount(null, null), '—')
})

test('blank currency yields em dash', () => {
  assert.equal(formatStripeAmount(100, '   '), '—')
})
