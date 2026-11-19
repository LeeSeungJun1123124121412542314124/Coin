import assert from 'node:assert/strict'
import { summarizeBtcPhase } from '../src/components/screens/dashboardPhase.ts'
import type { ChartResponse } from '../src/lib/learningApi.ts'

function candle(t: number, close: number, low: number, high: number) {
  return { open_time: t, open: close, high, low, close, volume: 1 }
}

function chart(candles: ReturnType<typeof candle>[], state: Partial<ChartResponse['state']> = {}): ChartResponse {
  return {
    candles,
    state: { cloud_position: null, tk_cross: null, chikou: null, future_cloud: null, ...state },
  } as unknown as ChartResponse
}

const three = [candle(1, 100, 95, 105), candle(2, 110, 98, 120), candle(3, 99, 90, 112)]

// 종가·전일 대비·고저·스파크라인
{
  const p = summarizeBtcPhase(chart(three))!
  assert.equal(p.close, 99)
  assert.equal(p.changePct, -10)
  assert.equal(p.low, 90)
  assert.equal(p.high, 120)
  const pts = p.spark.split(' ')
  assert.equal(pts.length, 3)
  assert.equal(pts[0].split(',')[0], '0')
  assert.equal(pts[2].split(',')[0], '300')
}

// 캔들 부족·null
assert.equal(summarizeBtcPhase(null), null)
assert.equal(summarizeBtcPhase(chart([candle(1, 100, 95, 105)])), null)

// 일목 상태 4칸
{
  const p = summarizeBtcPhase(chart(three))!
  assert.deepEqual(p.states.map(s => s.k), ['구름 위치', '전환·기준선', '후행스팬', '미래 구름'])
  assert.ok(p.states.every(s => s.v === '판단 불가' && s.tone === 'flat'))
}
{
  const p = summarizeBtcPhase(chart(three, { cloud_position: 'below', tk_cross: 'golden', chikou: 'above', future_cloud: 'bearish' }))!
  assert.deepEqual(p.states[0], { k: '구름 위치', v: '구름 아래', tone: 'down' })
  assert.deepEqual(p.states[1], { k: '전환·기준선', v: '골든크로스', tone: 'up' })
  assert.equal(p.states[2].tone, 'up')
  assert.equal(p.states[3].tone, 'down')
}
{
  const p = summarizeBtcPhase(chart(three, { cloud_position: 'inside', tk_cross: 'none' }))!
  assert.equal(p.states[0].tone, 'flat')
  assert.equal(p.states[1].tone, 'flat')
}
