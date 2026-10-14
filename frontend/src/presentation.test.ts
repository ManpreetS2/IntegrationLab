import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8')
const failuresTable = readFileSync(new URL('./components/FailuresTable.tsx', import.meta.url), 'utf8')

test('failure source tabs stay fully visible when they wrap', () => {
  const block = css.match(/\.segmented\s*\{([^}]+)\}/)
  assert.ok(block, 'segmented control styles are present')
  assert.match(block[1], /flex-wrap:\s*wrap/)
  assert.match(block[1], /overflow:\s*visible/)
  assert.doesNotMatch(block[1], /overflow:\s*hidden/)
})

test('create support case stays on one line', () => {
  assert.match(failuresTable, /className="secondary-button case-button"/)
  const block = css.match(/\.failures-table \.case-button\s*\{([^}]+)\}/)
  assert.ok(block, 'case button styles are present')
  assert.match(block[1], /white-space:\s*nowrap/)
  const drawer = readFileSync(new URL('./components/ledger/SupportCaseDrawer.tsx', import.meta.url), 'utf8')
  const ledgerCss = readFileSync(new URL('./ledger/ledger.css', import.meta.url), 'utf8')
  assert.match(drawer, /lg-case-button/)
  const ledgerBlock = ledgerCss.match(/\.lg-case-button\s*\{([^}]+)\}/)
  assert.ok(ledgerBlock, 'ledger case button styles are present')
  assert.match(ledgerBlock[1], /white-space:\s*nowrap/)
})
