import assert from 'node:assert/strict'

import {
  RESEARCH_CATEGORIES,
  getResearchCategoryColor,
  toStockSentimentDetailRows,
} from '../src/components/screens/researchView.ts'

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
