import assert from 'node:assert/strict'

import {
  RESEARCH_CATEGORIES,
  STOCK_SENTIMENT_INDEX_NOTES,
  getResearchCategoryColor,
  toKrStockFlowDetailRows,
  toStockSentimentDetailRows,
} from '../src/components/screens/researchView.ts'

// 주식수급 카테고리 칩·색
assert.ok(RESEARCH_CATEGORIES.includes('주식수급'))
assert.notEqual(getResearchCategoryColor('주식수급'), '#94a3b8')

// 주식수급 상세 행 — 억원을 조 단위로 표기
assert.deepEqual(
  toKrStockFlowDetailRows({
    foreign_20d: -30000,
    institution_20d: -20000,
    flow_total_20d: -50000,
    volume_ratio: 2.0,
    window_start: '2026-06-01',
    window_end: '2026-06-20',
    component_scores: { flow: 100, volume: 100 },
  }),
  [
    ['외국인 20일', '-3.0조'],
    ['기관 20일', '-2.0조'],
    ['합계 20일', '-5.0조'],
    ['거래대금 5/20일', '2.00x'],
    ['수급 점수', '100/100'],
    ['거래대금 점수', '100/100'],
  ],
)

// 값 없는 필드는 생략
assert.deepEqual(toKrStockFlowDetailRows({}), [])

// 주식심리 카드 지수 설명 — 지수당 한 줄
assert.equal(STOCK_SENTIMENT_INDEX_NOTES.length, 2)
assert.equal(STOCK_SENTIMENT_INDEX_NOTES[0][0], '공포탐욕지수')
assert.ok(STOCK_SENTIMENT_INDEX_NOTES[0][1].includes('공포'))
assert.ok(STOCK_SENTIMENT_INDEX_NOTES[0][1].includes('탐욕'))
assert.equal(STOCK_SENTIMENT_INDEX_NOTES[1][0], 'Put/Call 비율')
assert.ok(STOCK_SENTIMENT_INDEX_NOTES[1][1].includes('풋'))

assert.ok(RESEARCH_CATEGORIES.includes('주식심리'))
assert.equal(getResearchCategoryColor('주식심리'), '#38bdf8')

assert.deepEqual(
  toStockSentimentDetailRows({
    stock_fear_greed: {
      date: '2026-07-03',
      value: 42,
      rating: 'Fear',
      updated_at: '2026-07-04T00:00:00Z',
    },
    putcall: {
      date: '2026-07-03',
      total_pc: 0.91,
      equity_pc: 0.63,
      index_pc: 1.2,
      updated_at: '2026-07-04T00:00:00Z',
      used_pc: 0.63,
      source: 'equity_pc',
    },
    component_scores: {
      fear_greed: 42,
      putcall: 67,
    },
  }),
  [
    ['F&G', '42 (Fear)'],
    ['Equity P/C', '0.63'],
    ['Total P/C 참고', '0.91'],
    ['F&G 점수', '42/100'],
    ['P/C 점수', '67/100'],
  ],
)

assert.deepEqual(
  toStockSentimentDetailRows({
    stock_fear_greed: {
      date: '2026-07-03',
      value: 42,
      rating: 'Fear',
      updated_at: '2026-07-04T00:00:00Z',
    },
    putcall: {
      date: '2026-07-03',
      total_pc: 0.91,
      equity_pc: null,
      index_pc: 1.2,
      updated_at: '2026-07-04T00:00:00Z',
      used_pc: 0.91,
      source: 'total_pc',
    },
    component_scores: {
      fear_greed: 42,
      putcall: 67,
    },
  }),
  [
    ['F&G', '42 (Fear)'],
    ['Total P/C', '0.91'],
    ['F&G 점수', '42/100'],
    ['P/C 점수', '67/100'],
  ],
)
