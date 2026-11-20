import assert from 'node:assert/strict'
import { summarizeMood } from '../src/components/screens/dashboardMood.ts'

// 하락 2개 이상 → 주의
{
  const m = summarizeMood({ phaseTones: ['down', 'down', 'down', 'down'], spf: { direction: '하락', confidence: 62 }, warningCount: 2, fearGreed: 12 })
  assert.equal(m.ready, true)
  assert.equal(m.tone, 'caution')
  assert.equal(m.badge, '주의')
  assert.equal(m.sentence, '조심할 구간 — 하락 추세 · 중기 전망 하락')
  assert.equal(m.tally, '하락 2 · 주의 1 · 반등 1')
  assert.equal(m.basis.length, 4)
  assert.deepEqual(m.basis.map(b => b.key), ['phase', 'spf', 'warnings', 'fearGreed'])
}

// 상승 2개 + 하락 0개 → 우호
{
  const m = summarizeMood({ phaseTones: ['up', 'up', 'up', 'flat'], spf: { direction: '상승', confidence: 55 }, warningCount: 0, fearGreed: 50 })
  assert.equal(m.tone, 'favorable')
  assert.equal(m.badge, '우호')
  assert.equal(m.sentence, '우호적인 구간 — 상승 추세 · 중기 전망 상승')
  assert.equal(m.tally, '상승 2')
}

// 엇갈림 → 혼조, 꼬리말·집계 없음
{
  const m = summarizeMood({ phaseTones: ['up', 'down', 'flat', 'flat'], spf: { direction: '중립', confidence: 7 }, warningCount: 0, fearGreed: 50 })
  assert.equal(m.tone, 'mixed')
  assert.equal(m.badge, '혼조')
  assert.equal(m.sentence, '방향이 엇갈립니다')
  assert.equal(m.tally, '')
}

// 상승 2개여도 하락이 1개라도 있으면 혼조 (상승·하락은 국면·SPF 두 근거에서만 나오므로 상승 1 + 하락 1로 확인)
{
  const m = summarizeMood({ phaseTones: ['up', 'up', 'up', 'up'], spf: { direction: '상승', confidence: 60 }, warningCount: 0, fearGreed: 12 })
  assert.equal(m.tone, 'favorable')
  const mixed = summarizeMood({ phaseTones: ['up', 'up', 'up', 'up'], spf: { direction: '하락', confidence: 60 }, warningCount: 0, fearGreed: 50 })
  assert.equal(mixed.tone, 'mixed')
  assert.equal(mixed.tally, '하락 1 · 상승 1')
}

// 공포탐욕 80 → 과열 주의
{
  const m = summarizeMood({ phaseTones: null, spf: { direction: '중립', confidence: 0 }, warningCount: 0, fearGreed: 80 })
  const fg = m.basis.find(b => b.key === 'fearGreed')!
  assert.equal(fg.vote, 'caution')
  assert.equal(fg.tag, '과열 주의')
}

// 근거가 2개 미만이면 판정 보류
{
  const m = summarizeMood({ phaseTones: null, spf: null, warningCount: null, fearGreed: 12 })
  assert.equal(m.ready, false)
  assert.equal(m.basis.length, 1)
  assert.equal(m.sentence, '근거를 불러오는 중입니다')
}

// 국면 데이터 없음 + 나머지 3개 → 판정 가능
{
  const m = summarizeMood({ phaseTones: null, spf: { direction: '하락', confidence: 62 }, warningCount: 1, fearGreed: 50 })
  assert.equal(m.ready, true)
  assert.equal(m.basis.length, 3)
}

// 근거 문구 (시안): 국면 값·SPF 값·주의 신호 제목·공포탐욕 라벨
{
  const m = summarizeMood({
    phaseTones: ['down', 'down', 'down', 'flat'], phaseValue: '구름 아래 · 데드크로스',
    spf: { direction: '하락', confidence: 62 },
    warningCount: 2, warningTitles: ['VIX 28.4', '나스닥 −2.25%', '셋째'],
    fearGreed: 12, fearGreedLabel: '극단적 공포',
  })
  assert.deepEqual(m.basis.map(b => [b.label, b.value, b.tag]), [
    ['BTC 국면', '구름 아래 · 데드크로스', '▼ 하락'],
    ['SPF 중기 전망', '하락 · 신뢰도 62%', '▼ 하락'],
    ['주의 신호 2건', 'VIX 28.4 · 나스닥 −2.25%', '주의'],
    ['공포탐욕 12', '극단적 공포', '반등 신호'],
  ])
}
