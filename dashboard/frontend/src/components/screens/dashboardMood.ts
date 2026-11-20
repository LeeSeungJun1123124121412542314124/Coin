// 대시보드 "시장 분위기 한 줄" 판정 (순수 함수) — 규칙은 docs/plans/ui-v2-spec-2026-11-20.md 3절

export type Vote = 'down' | 'up' | 'caution' | 'rebound' | 'flat'

export interface MoodInput {
  /** 일목 4개 상태의 방향. null = 아직 못 받음 */
  phaseTones: ('up' | 'down' | 'flat')[] | null
  spf: { direction: string; confidence: number } | null
  warningCount: number | null
  fearGreed: number | null
  /** 근거 카드에 보일 문구 (판정에는 쓰지 않음) */
  phaseValue?: string
  warningTitles?: string[]
  fearGreedLabel?: string
}

export interface MoodBasis {
  key: 'phase' | 'spf' | 'warnings' | 'fearGreed'
  vote: Vote
  label: string
  value: string
  tag: string
}

export interface Mood {
  ready: boolean
  tone: 'caution' | 'favorable' | 'mixed'
  badge: string
  sentence: string
  tally: string
  basis: MoodBasis[]
}

// 꼬리말 구절
const PHRASE: Record<Exclude<MoodBasis['key'], 'warnings'>, Partial<Record<Vote, string>>> = {
  phase: { down: '하락 추세', up: '상승 추세' },
  spf: { down: '중기 전망 하락', up: '중기 전망 상승' },
  fearGreed: { rebound: '극단적 공포', caution: '과열 구간' },
}

function buildBasis(input: MoodInput): MoodBasis[] {
  const basis: MoodBasis[] = []

  if (input.phaseTones) {
    const downs = input.phaseTones.filter(t => t === 'down').length
    const ups = input.phaseTones.filter(t => t === 'up').length
    const vote: Vote = downs >= 3 ? 'down' : ups >= 3 ? 'up' : 'flat'
    basis.push({
      key: 'phase', vote, label: 'BTC 국면', value: input.phaseValue ?? '',
      tag: vote === 'down' ? '▼ 하락' : vote === 'up' ? '▲ 상승' : '혼조',
    })
  }

  if (input.spf) {
    const { direction, confidence } = input.spf
    const vote: Vote = direction === '하락' ? 'down' : direction === '상승' ? 'up' : 'flat'
    basis.push({
      key: 'spf', vote, label: 'SPF 중기 전망',
      value: direction ? `${direction} · 신뢰도 ${confidence}%` : '예측 없음',
      tag: vote === 'down' ? '▼ 하락' : vote === 'up' ? '▲ 상승' : '중립',
    })
  }

  if (input.warningCount !== null) {
    const n = input.warningCount
    basis.push({
      key: 'warnings', vote: n >= 1 ? 'caution' : 'flat',
      label: n >= 1 ? `주의 신호 ${n}건` : '주의 신호 없음',
      value: n >= 1 ? (input.warningTitles ?? []).slice(0, 2).join(' · ') : '특이 신호 없음',
      tag: n >= 1 ? '주의' : '없음',
    })
  }

  if (input.fearGreed !== null) {
    const v = input.fearGreed
    const vote: Vote = v <= 25 ? 'rebound' : v >= 75 ? 'caution' : 'flat'
    basis.push({
      key: 'fearGreed', vote, label: `공포탐욕 ${v}`, value: input.fearGreedLabel ?? '',
      tag: vote === 'rebound' ? '반등 신호' : vote === 'caution' ? '과열 주의' : '중립',
    })
  }

  return basis
}

export function summarizeMood(input: MoodInput): Mood {
  const basis = buildBasis(input)
  const count = (v: Vote) => basis.filter(b => b.vote === v).length

  // 근거 4개 중 2개 미만이면 판정 보류
  if (basis.length < 2) {
    return { ready: false, tone: 'mixed', badge: '확인 중', sentence: '근거를 불러오는 중입니다', tally: '', basis }
  }

  const downs = count('down')
  const ups = count('up')
  const [tone, badge, head] =
    downs >= 2 ? ['caution', '주의', '조심할 구간'] as const
    : ups >= 2 && downs === 0 ? ['favorable', '우호', '우호적인 구간'] as const
    : ['mixed', '혼조', '방향이 엇갈립니다'] as const

  const tail = basis
    .filter(b => b.vote !== 'flat')
    .map(b => b.key === 'warnings' ? `주의 신호 ${input.warningCount}건` : PHRASE[b.key][b.vote] ?? '')
    .filter(Boolean)
    .slice(0, 2)
    .join(' · ')

  const tally = ([['하락', downs], ['상승', ups], ['주의', count('caution')], ['반등', count('rebound')]] as const)
    .filter(([, n]) => n > 0)
    .map(([name, n]) => `${name} ${n}`)
    .join(' · ')

  return { ready: true, tone, badge, sentence: tail ? `${head} — ${tail}` : head, tally, basis }
}
