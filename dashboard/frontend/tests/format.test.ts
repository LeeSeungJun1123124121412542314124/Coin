import assert from 'node:assert/strict'
import { fmtFixed, fmtSignedPct, fmtIndex, fmtCoinPrice } from '../src/lib/format.ts'

assert.equal(fmtFixed(23879.199, 2), '23,879.20')
assert.equal(fmtFixed(null, 2), '—')
assert.equal(fmtFixed(-1.5, 2), '−1.50')
assert.equal(fmtFixed(-1234.5, 1), '−1,234.5')
assert.equal(fmtIndex(-12.3), '−12.30')
assert.equal(fmtCoinPrice(-5), '$−5.00')
assert.equal(fmtSignedPct(1.3), '+1.30%')
assert.equal(fmtSignedPct(-2.27), '\u22122.27%')
assert.equal(fmtSignedPct(0), '0.00%')
assert.equal(fmtIndex(657.5), '657.50')
assert.equal(fmtCoinPrice(61937.2), '$61,937')
assert.equal(fmtCoinPrice(72.76), '$72.76')
assert.equal(fmtCoinPrice(0.3432), '$0.343')
assert.equal(fmtCoinPrice(null), '—')

assert.equal(fmtFixed(-0.001, 2), '0.00')
assert.equal(fmtFixed(-0.004, 0), '0')
assert.equal(fmtFixed(NaN, 2), '—')
assert.equal(fmtFixed(undefined, 2), '—')
assert.equal(fmtCoinPrice(NaN), '—')
assert.equal(fmtSignedPct(NaN), '—')
assert.equal(fmtSignedPct(-0.001), '0.00%')

console.log('format.test.ts 통과')
