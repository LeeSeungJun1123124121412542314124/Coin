import assert from 'node:assert/strict'
import { fmtFixed, fmtSignedPct, fmtIndex, fmtCoinPrice } from '../src/lib/format.ts'

assert.equal(fmtFixed(23879.199, 2), '23,879.20')
assert.equal(fmtFixed(null, 2), '—')
assert.equal(fmtSignedPct(1.3), '+1.30%')
assert.equal(fmtSignedPct(-2.27), '\u22122.27%')
assert.equal(fmtSignedPct(0), '0.00%')
assert.equal(fmtIndex(657.5), '657.50')
assert.equal(fmtCoinPrice(61937.2), '$61,937')
assert.equal(fmtCoinPrice(72.76), '$72.76')
assert.equal(fmtCoinPrice(0.3432), '$0.343')
assert.equal(fmtCoinPrice(null), '—')

console.log('format.test.ts 통과')
