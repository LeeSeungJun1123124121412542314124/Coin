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
