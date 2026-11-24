import assert from 'node:assert/strict'
import {
  ladderPosition,
  signalTally,
  splitMoodSentence,
  toBotNews,
  toDiffRows,
  toSignalCells,
} from '../src/components/screens/homeBriefView.ts'

const cat = (key: string, name: string, level: string, score: number, extra: Record<string, unknown> = {}) => ({
  key, name, level, score, summary: `${name} 요약`, updated_at: '2026-11-24T01:00:00+00:00', details: {}, ...extra,
})
const prev = (score: number, level: string) => ({ prev: { date: '2026-11-23', days_ago: 1, score, level }, week: null })

const categories = [
  cat('macro', '매크로', 'bullish', 40),
  cat('onchain', '온체인', 'neutral', 40, { compare: prev(40, 'neutral') }),
  cat('kr_stock_flow', '주식수급', 'critical', 75, { compare: prev(75, 'critical') }),
  cat('stock_sentiment', '주식심리', 'neutral', 31, { compare: prev(24, 'warning') }),
  cat('market', '시장분석', 'warning', 65),
  cat('bot_heatmap', '청산 히트맵', 'neutral', 0, {
    observed: true, summary: '11-24 09:13 기준 · 현재가 $61,150', updated_at: '2026-11-24T00:13:00+00:00',
    details: { levels: { price: 61150, long_price: 57352, short_price: 64001 } },
  }),
]

// 신호판: 점수 분석만, 급한 순(위험 → 경계 → 약세 → 중립 → 강세), 등급 이름을 붙인다
const cells = toSignalCells(categories)
assert.deepEqual(cells.map((c) => c.name), ['주식수급', '시장분석', '온체인', '주식심리', '매크로'])
assert.deepEqual(cells.map((c) => c.label), ['위험', '경계', '중립', '중립', '강세'])
assert.equal(cells.some((c) => c.name === '청산 히트맵'), false)

// 집계 줄: 0인 등급은 뺀다
assert.equal(signalTally(cells), '위험 1 · 경계 1 · 중립 2 · 강세 1')
assert.equal(signalTally([]), '')

// 달라진 것: 어제와 점수·등급이 달라진 항목이 먼저(변화 큰 순), 나머지는 급한 순. 이전 기록이 없으면 "–"
const rows = toDiffRows(categories, 4)
assert.deepEqual(rows.map((r) => r.name), ['주식심리', '주식수급', '시장분석', '온체인'])
assert.deepEqual(rows.map((r) => r.delta), ['24 → 31', '75 → 75', '–', '40 → 40'])
assert.equal(rows[0].label, '중립')
assert.equal(rows[0].summary, '주식심리 요약')
assert.equal(toDiffRows(categories, 2).length, 2)

// 봇 소식: 봇 관찰 카드만, 시각은 한국 시간
assert.deepEqual(toBotNews(categories), [
  { key: 'bot_heatmap', name: '청산 히트맵', time: '11-24 09:13', summary: '11-24 09:13 기준 · 현재가 $61,150' },
])

// 청산 구간 막대: 아래 롱 ~ 위 숏 사이에서 현재가의 위치(%)와 각 구간까지 거리(%)
assert.deepEqual(ladderPosition({ price: 61150, long_price: 57352, short_price: 64001 }, 61205), {
  percent: 57.9, long: 57352, short: 64001, longGap: -6.3, shortGap: 4.6,
})
// 실시간 가격이 없으면 리포트의 현재가로
assert.equal(ladderPosition({ price: 61150, long_price: 57352, short_price: 64001 }, null)?.percent, 57.1)
// 구간을 벗어나면 끝에 붙인다
assert.equal(ladderPosition({ price: 61150, long_price: 57352, short_price: 64001 }, 70000)?.percent, 100)
assert.equal(ladderPosition({ price: 61150, long_price: 57352, short_price: 64001 }, 50000)?.percent, 0)
// 값이 빠졌거나 순서가 뒤집히면 그리지 않는다
assert.equal(ladderPosition({ price: 61150, long_price: 57352 }, 61205), null)
assert.equal(ladderPosition({ price: 61150, long_price: 64001, short_price: 57352 }, 61205), null)
assert.equal(ladderPosition(undefined, 61205), null)

// 판단 문장을 큰 제목과 근거 꼬리말로 나눈다
assert.deepEqual(splitMoodSentence('조심할 구간 — 하락 추세 · 중기 전망 하락'), { headline: '조심할 구간입니다.', tail: '하락 추세 · 중기 전망 하락' })
assert.deepEqual(splitMoodSentence('우호적인 구간'), { headline: '우호적인 구간입니다.', tail: '' })
assert.deepEqual(splitMoodSentence('방향이 엇갈립니다 — 극단적 공포'), { headline: '방향이 엇갈립니다.', tail: '극단적 공포' })
assert.deepEqual(splitMoodSentence('근거를 불러오는 중입니다'), { headline: '근거를 불러오는 중입니다.', tail: '' })

console.log('homeBriefView ok')
