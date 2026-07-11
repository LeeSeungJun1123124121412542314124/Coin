export const RESEARCH_CATEGORY_COLORS: Record<string, string> = {
  '매크로': '#60a5fa',
  '온체인': '#4ade80',
  '파생상품': '#f97316',
  '알트코인': '#a78bfa',
  '기술적분석': '#f59e0b',
  '시장분석': '#f87171',
  '기타': '#94a3b8',
  '반도체 정점': '#2dd4bf',
  '주식심리': '#38bdf8',
  '주식수급': '#34d399',
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

export function getResearchCategoryColor(category: string) {
  return category === '전체' ? '#60a5fa' : (RESEARCH_CATEGORY_COLORS[category] ?? '#94a3b8')
}

export function toStockSentimentDetailRows(details: StockSentimentDetails): Array<[string, string]> {
  const rows: Array<[string, string]> = []
  const fearGreed = details.stock_fear_greed
  const putcall = details.putcall
  const scores = details.component_scores

  if (fearGreed?.value != null) {
    const rating = fearGreed.rating ? ` (${fearGreed.rating})` : ''
    rows.push(['F&G', `${fearGreed.value}${rating}`])
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
    rows.push(['F&G 점수', `${scores.fear_greed}/100`])
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
