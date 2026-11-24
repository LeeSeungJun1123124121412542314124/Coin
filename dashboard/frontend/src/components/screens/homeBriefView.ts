// 홈 머리 구역(신호판·달라진 것·봇 소식·청산 구간 막대)에 쓰는 순수 함수
// 스펙: docs/plans/light-redesign-spec-2026-11-24.md 6절
import { formatKst } from './botReportView.ts'
import { LEVEL_LABELS, sortByUrgency, type CategoryCompare } from './researchView.ts'

export interface BriefCategory {
  key: string
  name: string
  level: string
  score: number
  summary: string
  updated_at: string
  details: Record<string, unknown>
  compare?: CategoryCompare | null
  observed?: boolean
}

export interface SignalCell {
  key: string
  name: string
  level: string
  label: string
}

// 신호판: 점수 분석 카테고리마다 한 칸, 급한 순
export function toSignalCells(categories: BriefCategory[]): SignalCell[] {
  return sortByUrgency(categories.filter((c) => !c.observed)).map((c) => ({
    key: c.key, name: c.name, level: c.level, label: LEVEL_LABELS[c.level] ?? c.level,
  }))
}

// "위험 1 · 경계 1 · 중립 4 · 강세 2" — 0인 등급은 뺀다
export function signalTally(cells: SignalCell[]): string {
  return ['critical', 'warning', 'bearish', 'neutral', 'bullish']
    .map((level) => [LEVEL_LABELS[level], cells.filter((c) => c.level === level).length] as const)
    .filter(([, count]) => count > 0)
    .map(([label, count]) => `${label} ${count}`)
    .join(' · ')
}

export interface DiffRow extends SignalCell {
  summary: string
  /** "어제 점수 → 오늘 점수". 이전 기록이 없으면 "–" */
  delta: string
}

// 어제와 달라진 것: 점수·등급이 달라진 항목이 먼저(변화 큰 순), 나머지는 급한 순
export function toDiffRows(categories: BriefCategory[], limit: number): DiffRow[] {
  const change = (c: BriefCategory): number => {
    const before = c.compare?.prev
    if (!before || before.score == null) return 0
    return Math.abs(c.score - before.score) || (before.level !== c.level ? 0.5 : 0)
  }
  const sorted = sortByUrgency(categories.filter((c) => !c.observed))
  const changed = sorted.filter((c) => change(c) > 0).sort((a, b) => change(b) - change(a))
  const rest = sorted.filter((c) => change(c) === 0)
  return [...changed, ...rest].slice(0, limit).map((c) => {
    const before = c.compare?.prev
    return {
      key: c.key, name: c.name, level: c.level, label: LEVEL_LABELS[c.level] ?? c.level, summary: c.summary,
      delta: before && before.score != null ? `${before.score} → ${c.score}` : '–',
    }
  })
}

export interface BotNewsItem {
  key: string
  name: string
  time: string
  summary: string
}

// 봇이 보낸 소식: 봇 관찰 카드
export function toBotNews(categories: BriefCategory[]): BotNewsItem[] {
  return categories.filter((c) => c.observed).map((c) => ({
    key: c.key, name: c.name, time: formatKst(c.updated_at), summary: c.summary,
  }))
}

export interface Ladder {
  /** 아래 롱 구간(0) ~ 위 숏 구간(100) 사이에서 현재가의 위치 */
  percent: number
  long: number
  short: number
  /** 현재가에서 각 구간까지 거리(%) */
  longGap: number
  shortGap: number
}

const round1 = (v: number) => Math.round(v * 10) / 10

// 청산 구간 막대 — 히트맵 카드의 숫자(details.levels)가 다 있을 때만 그린다. 현재가는 실시간 값이 있으면 그것을 쓴다
export function ladderPosition(levels: unknown, livePrice: number | null | undefined): Ladder | null {
  const value = (levels ?? {}) as { price?: unknown; long_price?: unknown; short_price?: unknown }
  const long = value.long_price
  const short = value.short_price
  const price = livePrice ?? value.price
  if (typeof long !== 'number' || typeof short !== 'number' || typeof price !== 'number') return null
  if (!(long < short) || price <= 0) return null
  const percent = Math.min(100, Math.max(0, ((price - long) / (short - long)) * 100))
  return {
    percent: round1(percent), long, short,
    longGap: round1(((long - price) / price) * 100),
    shortGap: round1(((short - price) / price) * 100),
  }
}

// 판단 문장 "조심할 구간 — 하락 추세 · …"을 큰 제목과 꼬리말로 나눈다
export function splitMoodSentence(sentence: string): { headline: string; tail: string } {
  const [head, ...rest] = sentence.split(' — ')
  return { headline: head.endsWith('다') ? `${head}.` : `${head}입니다.`, tail: rest.join(' — ') }
}
