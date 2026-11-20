import assert from 'node:assert/strict'
import { directionText } from '../src/components/screens/leaderboardView.ts'

// 실제 API 값: 롱='long', 숏='short', 없음=키 없음/null
assert.deepEqual(directionText({ BTC: 'long', ETH: 'long', SOL: 'long' }), { text: '전 종목 롱', tone: 'up' })
assert.deepEqual(directionText({ BTC: 'short', ETH: 'short', SOL: 'short' }), { text: '전 종목 숏', tone: 'down' })
assert.deepEqual(directionText({ BTC: null, ETH: null, SOL: null }), { text: '관망', tone: 'flat' })
assert.deepEqual(directionText({ BTC: 'long', ETH: 'short', SOL: 'short' }), { text: 'BTC 롱 · ETH·SOL 숏', tone: 'flat' })
assert.deepEqual(directionText({ BTC: 'long', ETH: null, SOL: 'long' }), { text: 'BTC·SOL 롱', tone: 'up' })
assert.deepEqual(directionText({}), { text: '관망', tone: 'flat' })
