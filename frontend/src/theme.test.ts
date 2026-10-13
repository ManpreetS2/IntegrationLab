import assert from 'node:assert/strict'
import test from 'node:test'
import { readAppearance, resolveTheme } from './theme.ts'

test('system appearance follows the OS scheme', () => {
  assert.equal(resolveTheme('system', false), 'light')
  assert.equal(resolveTheme('system', true), 'dark')
})

test('manual appearance ignores the OS scheme', () => {
  assert.equal(resolveTheme('light', true), 'light')
  assert.equal(resolveTheme('dark', false), 'dark')
})

test('unknown stored values fall back to system', () => {
  assert.equal(readAppearance({ getItem: () => 'sepia' }), 'system')
  assert.equal(readAppearance({ getItem: () => null }), 'system')
  assert.equal(readAppearance(null), 'system')
})

test('stored light and dark preferences are kept', () => {
  assert.equal(readAppearance({ getItem: () => 'dark' }), 'dark')
  assert.equal(readAppearance({ getItem: () => 'light' }), 'light')
})
