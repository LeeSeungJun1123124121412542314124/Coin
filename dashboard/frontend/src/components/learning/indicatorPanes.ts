import { C } from '../../lib/theme.ts'

export type PaneKey = 'volume' | 'rsi' | 'macd'

// 켜진 아래 칸을 거래량 → RSI → MACD 순서로 pane 1번부터 배정 (0번은 본 칸)
export function paneLayout(enabled: Record<PaneKey, boolean>): { key: PaneKey; index: number }[] {
  const keys: PaneKey[] = ['volume', 'rsi', 'macd']
  return keys.filter(k => enabled[k]).map((key, i) => ({ key, index: i + 1 }))
}

// 본 칸 높이(base)는 그대로, 아래 칸마다 paneHeight씩 전체 높이 증가
export const chartHeight = (base: number, paneCount: number, paneHeight = 110) => base + paneCount * paneHeight

// 이동평균 색 — 스펙 순서, 7번째부터 반복
const MA_COLORS = [C.accent, C.info, C.violet, C.warn, C.ok, C.text2]
export const maColor = (i: number) => MA_COLORS[i % MA_COLORS.length]
