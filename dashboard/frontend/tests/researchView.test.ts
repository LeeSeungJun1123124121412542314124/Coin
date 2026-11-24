import assert from 'node:assert/strict'

import { C } from '../src/lib/theme.ts'

import {
  RESEARCH_CATEGORIES,
  STOCK_SENTIMENT_INDEX_NOTES,
  getResearchCategoryColor,
  sortByUrgency,
  toCompareLines,
  toKrStockFlowDetailRows,
  toStockSentimentDetailRows,
} from '../src/components/screens/researchView.ts'

// 주식수급 카테고리 칩·색
assert.ok(RESEARCH_CATEGORIES.includes('주식수급'))
assert.notEqual(getResearchCategoryColor('주식수급'), C.text2)

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

// 최신 영업일·전일 수급(억원)과 20일 합계의 전일 대비 변화 — 20일 누적만으로는 날마다 같아 보인다
assert.deepEqual(
  toKrStockFlowDetailRows({
    latest_date: '2026-11-23',
    latest_foreign: -2380,
    latest_institution: 1879,
    prev_date: '2026-11-20',
    prev_foreign: -10956,
    prev_institution: -9330,
    flow_total_20d: -91000,
    flow_total_20d_change: -501,
  }),
  [
    ['외국인 11-23', '-2,380억'],
    ['기관 11-23', '+1,879억'],
    ['외국인 11-20', '-10,956억'],
    ['기관 11-20', '-9,330억'],
    ['합계 20일', '-9.1조'],
    ['합계 20일 전일 대비', '-501억'],
  ],
)

// 전일 대비 변화를 만들 수 없으면(null) 그 줄만 생략
assert.deepEqual(
  toKrStockFlowDetailRows({ flow_total_20d: -10000, flow_total_20d_change: null }),
  [['합계 20일', '-1.0조']],
)

// 어제·7일 전 대비 줄 (docs/plans/research-compare-spec-2026-11-24.md)
{
  const labels = { neutral: '중립', warning: '경계' }
  // 등급 유지, 점수 상승
  assert.deepEqual(
    toCompareLines({
      score: 42,
      level: 'neutral',
      compare: {
        prev: { date: '2026-11-23', days_ago: 1, score: 38, level: 'neutral', summary: '유입/유출 비율 0.98' },
        week: { date: '2026-11-17', days_ago: 7, score: 35, level: 'neutral' },
      },
    }, labels),
    {
      prevLine: '어제 38 → 오늘 42 (▲4) · 등급 그대로',
      weekLine: '7일 전 35 (▲7)',
      prevSummary: { label: '어제', text: '유입/유출 비율 0.98' },
    },
  )
  // 등급 변경, 점수 하락, 어제가 아닌 저장분(주말 등) — 실제 일수로 표시
  assert.deepEqual(
    toCompareLines({
      score: 50,
      level: 'neutral',
      compare: {
        prev: { date: '2026-11-21', days_ago: 3, score: 61, level: 'warning', summary: 'VIX 26.6' },
        week: { date: '2026-11-15', days_ago: 9, score: 50, level: 'neutral' },
      },
    }, labels),
    {
      prevLine: '3일 전 61 → 오늘 50 (▼11) · 등급 경계 → 중립',
      weekLine: '9일 전 50 (–)',
      prevSummary: { label: '3일 전', text: 'VIX 26.6' },
    },
  )
  // 모르는 등급은 값 그대로, 7일 전 저장분만 없는 경우
  assert.deepEqual(
    toCompareLines({
      score: 10,
      level: 'bullish',
      compare: { prev: { date: '2026-11-23', days_ago: 1, score: 10, level: 'neutral', summary: '' }, week: null },
    }, labels),
    {
      prevLine: '어제 10 → 오늘 10 (–) · 등급 중립 → bullish',
      weekLine: null,
      prevSummary: null, // 빈 요약은 나란히 보여줄 게 없다
    },
  )
  // 이전 저장분이 없으면(저장 시작 첫날, 비교값 조회 실패) 아무 줄도 만들지 않는다
  const none = { prevLine: null, weekLine: null, prevSummary: null }
  assert.deepEqual(toCompareLines({ score: 42, level: 'neutral', compare: { prev: null, week: null } }, labels), none)
  assert.deepEqual(toCompareLines({ score: 42, level: 'neutral' }, labels), none)
  assert.deepEqual(toCompareLines({ score: 42, level: 'neutral', compare: null }, labels), none)
}

// 봇 관찰 카드 (docs/plans/bot-reports-spec-2026-11-24.md 7절)
{
  // 분류 칩과 색
  for (const name of ['ETF 수급', '청산 히트맵', '고래 소식']) {
    assert.ok(RESEARCH_CATEGORIES.includes(name), name)
    assert.notEqual(getResearchCategoryColor(name), C.text2)
  }
  // 점수가 없으므로 점수 줄은 만들지 않고, 이전 요약만 나란히 보여준다
  assert.deepEqual(
    toCompareLines({
      score: 0,
      level: 'neutral',
      observed: true,
      compare: { prev: { date: '2026-11-23', days_ago: 1, summary: '11-23 09:17 기준 · 현재가 $58,970' }, week: null },
    }, { neutral: '중립' }),
    { prevLine: null, weekLine: null, prevSummary: { label: '어제', text: '11-23 09:17 기준 · 현재가 $58,970' } },
  )
  // 정렬 — 점수 있는 카드가 모두 먼저, 봇 관찰 카드는 받은 순서 그대로 맨 뒤
  const cards = [
    { id: 'etf', level: 'neutral', score: 0, observed: true },
    { id: 'a', level: 'bullish', score: 10 },
    { id: 'heat', level: 'neutral', score: 0, observed: true },
    { id: 'b', level: 'critical', score: 80 },
  ]
  assert.deepEqual(sortByUrgency(cards).map(c => c.id), ['b', 'a', 'etf', 'heat'])
}

// 주식심리 카드 지수 설명 — 지수당 한 줄
assert.equal(STOCK_SENTIMENT_INDEX_NOTES.length, 2)
assert.equal(STOCK_SENTIMENT_INDEX_NOTES[0][0], '공포탐욕지수')
assert.ok(STOCK_SENTIMENT_INDEX_NOTES[0][1].includes('공포'))
assert.ok(STOCK_SENTIMENT_INDEX_NOTES[0][1].includes('탐욕'))
assert.equal(STOCK_SENTIMENT_INDEX_NOTES[1][0], 'Put/Call 비율')
assert.ok(STOCK_SENTIMENT_INDEX_NOTES[1][1].includes('풋'))

assert.ok(RESEARCH_CATEGORIES.includes('주식심리'))
assert.equal(getResearchCategoryColor('주식심리'), C.info)

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
    ['F&G', '42.0 (Fear)'],
    ['Equity P/C', '0.63'],
    ['Total P/C 참고', '0.91'],
    ['F&G 점수', '42.0/100'],
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
    ['F&G', '42.0 (Fear)'],
    ['Total P/C', '0.91'],
    ['F&G 점수', '42.0/100'],
    ['P/C 점수', '67/100'],
  ],
)

// 급한 순 정렬 — 위험(critical) → 경계(warning) → 약세(bearish) → 중립(neutral) → 그 외
{
  const cards = [
    { id: 'a', level: 'neutral', score: 90 },
    { id: 'b', level: 'critical', score: 10 },
    { id: 'c', level: 'unknown', score: 99 },
    { id: 'd', level: 'warning', score: 40 },
    { id: 'e', level: 'warning', score: 70 },
    { id: 'f', level: 'bearish', score: 55 },
    { id: 'g', level: 'bullish', score: 20 },
    { id: 'h', level: 'critical', score: 80 },
  ]
  const snapshot = JSON.stringify(cards)
  const sorted = sortByUrgency(cards)
  // 등급 순서 + 같은 등급은 점수 내림차순, 모르는 등급·강세는 맨 뒤(점수 내림차순)
  assert.deepEqual(sorted.map(c => c.id), ['h', 'b', 'e', 'd', 'f', 'a', 'c', 'g'])
  // 원본 불변
  assert.equal(JSON.stringify(cards), snapshot)
  assert.notEqual(sorted, cards)
  // 빈 배열
  assert.deepEqual(sortByUrgency([]), [])
}

// 주식심리 상세 행 — 긴 소수는 1자리로(정수는 그대로)
assert.deepEqual(
  toStockSentimentDetailRows({
    stock_fear_greed: { value: 25.2297455968689, rating: 'Fear' },
    component_scores: { fear_greed: 25.2297455968689 },
  }),
  [
    ['F&G', '25.2 (Fear)'],
    ['F&G 점수', '25.2/100'],
  ],
)
