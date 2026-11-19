import assert from 'node:assert/strict'

import { C } from '../src/lib/theme.ts'
import { chartHeight, maColor, paneLayout } from '../src/components/learning/indicatorPanes.ts'

// 켜진 아래 칸만 거래량 → RSI → MACD 순서로 pane 1번부터
assert.deepEqual(paneLayout({ volume: false, rsi: true, macd: true }), [
  { key: 'rsi', index: 1 },
  { key: 'macd', index: 2 },
])
assert.deepEqual(paneLayout({ volume: false, rsi: false, macd: false }), [])
assert.deepEqual(paneLayout({ volume: true, rsi: true, macd: true }).map(p => p.index), [1, 2, 3])

// 본 칸 높이는 그대로, 칸 하나당 110px 증가
assert.equal(chartHeight(460, 2), 680)
assert.equal(chartHeight(460, 0), 460)

// 이동평균 색은 스펙 순서, 7번째부터 반복
assert.equal(maColor(0), C.accent)
assert.equal(maColor(5), C.text2)
assert.equal(maColor(6), maColor(0))

console.log('indicatorPanes ok')
