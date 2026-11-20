import { C } from '../../lib/theme.ts'
import { fmtFixed } from '../../lib/format.ts'

// 카테고리 구분 색 — 상승/하락 의미 없는 구분용이라 의미 토큰 hex를 그대로 사용
export const RESEARCH_CATEGORY_COLORS: Record<string, string> = {
  '매크로': C.info,
  '온체인': C.ok,
  '파생상품': C.warn,
  '알트코인': C.violet,
  '기술적분석': C.warnText,
  '시장분석': C.danger,
  '기타': C.text2,
  '반도체 정점': C.accent,
  '주식심리': C.info,
  '주식수급': C.ok,
}

export const RESEARCH_CATEGORIES = [
  '전체',
  '매크로',
  '온체인',
  '파생상품',
  '알트코인',
  '기술적분석',
  '시장분석',
  '기타',
  '반도체 정점',
  '주식심리',
  '주식수급',
]

// 주식심리 카드 펼침 영역에 표시하는 지수별 한 줄 설명
export const STOCK_SENTIMENT_INDEX_NOTES: Array<[string, string]> = [
  ['공포탐욕지수', 'CNN이 산출하는 미국 주식 투자심리 (0~100). 0에 가까울수록 극단적 공포, 100에 가까울수록 극단적 탐욕 — 높을수록 과열·고점 경계'],
  ['Put/Call 비율', 'CBOE 풋옵션/콜옵션 거래량 비율. 1.0 초과면 하락 베팅 우세(공포), 0.7 미만이면 낙관 과열 — 낮을수록 과열 신호'],
]

interface StockSentimentDetails {
  stock_fear_greed?: {
    value?: number | null
    rating?: string | null
  } | null
  putcall?: {
    total_pc?: number | null
    equity_pc?: number | null
  } | null
  component_scores?: {
    fear_greed?: number | null
    putcall?: number | null
  } | null
}

// 급한 정도 순서: 위험 → 경계 → 약세 → 중립 → 그 외(강세·모르는 값)
const URGENCY_ORDER = ['critical', 'warning', 'bearish', 'neutral']

function urgencyRank(level: string): number {
  const i = URGENCY_ORDER.indexOf(level)
  return i === -1 ? URGENCY_ORDER.length : i
}

// 급한 순 정렬 — 같은 등급은 점수 내림차순, 원본 배열은 바꾸지 않는다
export function sortByUrgency<T extends { level: string; score: number }>(cards: T[]): T[] {
  return [...cards].sort((a, b) => urgencyRank(a.level) - urgencyRank(b.level) || b.score - a.score)
}

export function getResearchCategoryColor(category: string) {
  return category === '전체' ? C.accent : (RESEARCH_CATEGORY_COLORS[category] ?? C.text2)
}

export function toStockSentimentDetailRows(details: StockSentimentDetails): Array<[string, string]> {
  const rows: Array<[string, string]> = []
  const fearGreed = details.stock_fear_greed
  const putcall = details.putcall
  const scores = details.component_scores

  if (fearGreed?.value != null) {
    const rating = fearGreed.rating ? ` (${fearGreed.rating})` : ''
    rows.push(['F&G', `${fmtFixed(fearGreed.value, 1)}${rating}`])
  }

  if (putcall?.equity_pc != null) {
    rows.push(['Equity P/C', String(putcall.equity_pc)])
    if (putcall.total_pc != null) {
      rows.push(['Total P/C 참고', String(putcall.total_pc)])
    }
  } else if (putcall?.total_pc != null) {
    rows.push(['Total P/C', String(putcall.total_pc)])
  }

  if (scores?.fear_greed != null) {
    rows.push(['F&G 점수', `${fmtFixed(scores.fear_greed, 1)}/100`])
  }
  if (scores?.putcall != null) {
    rows.push(['P/C 점수', `${scores.putcall}/100`])
  }

  return rows
}

interface KrStockFlowDetails {
  foreign_20d?: number | null
  institution_20d?: number | null
  flow_total_20d?: number | null
  volume_ratio?: number | null
  window_start?: string | null
  window_end?: string | null
  component_scores?: {
    flow?: number | null
    volume?: number | null
  } | null
}

function formatEokAsJo(value: number): string {
  const jo = value / 10_000
  return `${jo >= 0 ? '+' : ''}${jo.toFixed(1)}조`
}

export function toKrStockFlowDetailRows(details: KrStockFlowDetails): Array<[string, string]> {
  const rows: Array<[string, string]> = []
  const scores = details.component_scores

  if (details.foreign_20d != null) {
    rows.push(['외국인 20일', formatEokAsJo(details.foreign_20d)])
  }
  if (details.institution_20d != null) {
    rows.push(['기관 20일', formatEokAsJo(details.institution_20d)])
  }
  if (details.flow_total_20d != null) {
    rows.push(['합계 20일', formatEokAsJo(details.flow_total_20d)])
  }
  if (details.volume_ratio != null) {
    rows.push(['거래대금 5/20일', `${details.volume_ratio.toFixed(2)}x`])
  }
  if (scores?.flow != null) {
    rows.push(['수급 점수', `${scores.flow}/100`])
  }
  if (scores?.volume != null) {
    rows.push(['거래대금 점수', `${scores.volume}/100`])
  }

  return rows
}
