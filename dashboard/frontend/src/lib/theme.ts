/** 레벨별 텍스트 색상 */
export const LEVEL_COLORS: Record<string, string> = {
  critical: '#ef4444',
  warning:  '#f97316',
  bearish:  '#f87171',
  bullish:  '#4ade80',
  neutral:  '#94a3b8',
}

/** 레벨별 배경색 */
export const LEVEL_BG: Record<string, string> = {
  critical: 'rgba(239,68,68,0.10)',
  warning:  'rgba(249,115,22,0.10)',
  bearish:  'rgba(248,113,113,0.08)',
  bullish:  'rgba(74,222,128,0.08)',
  neutral:  'rgba(100,116,139,0.08)',
}

/** 레벨별 테두리색 */
export const LEVEL_BORDER: Record<string, string> = {
  critical: 'rgba(239,68,68,0.4)',
  warning:  'rgba(249,115,22,0.3)',
  bearish:  'rgba(248,113,113,0.25)',
  bullish:  'rgba(74,222,128,0.25)',
  neutral:  'rgba(100,116,139,0.2)',
}
