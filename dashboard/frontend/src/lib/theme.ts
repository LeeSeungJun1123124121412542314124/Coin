/** 디자인 토큰 hex 값 (src/index.css :root 변수와 같은 값 — recharts·lightweight-charts용) */
export const C = {
  bg: '#F8F6F1',
  bgInset: '#F1EEE6',
  surface: '#FDFCF9',
  surface2: '#EFEBE2',
  border: '#DDD8CC',
  line: '#E7E2D7',
  segActive: '#FFFFFF',
  borderStrong: '#BDB6A6',
  text: '#25231F',
  text2: '#45413A',
  text3: '#6A655C',
  accent: '#7A5A14',
  up: '#B93A2E',
  down: '#2459B0',
  warn: '#9C4A10',
  warnText: '#9C4A10',
  ok: '#2C5C45',
  danger: '#A8392B',
  violet: '#6B4BB8',
  info: '#3F56B5',
  neutralSeries: '#8F897E',
} as const

/** 한국식 등락 색: 상승 = 빨강, 하락 = 파랑, 0·결측 = 보조 글자색 */
export function changeColor(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v) || v === 0) return C.text2
  return v > 0 ? C.up : C.down
}

/** 등락 화살표 */
export function changeArrow(v: number | null | undefined): '▲' | '▼' | '–' {
  if (v == null || Number.isNaN(v) || v === 0) return '–'
  return v > 0 ? '▲' : '▼'
}

/** '#RRGGBB' → 'rgba(r,g,b,alpha)' */
export function softBg(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}

/** 레벨별 텍스트 색상 — 강세는 등락색(빨강)이 아니라 초록: 위험(빨강)과 헷갈리지 않게 */
export const LEVEL_COLORS: Record<string, string> = {
  critical: C.danger,
  warning:  C.warn,
  bearish:  C.down,
  bullish:  C.ok,
  neutral:  C.text2,
}

/** 레벨별 배경색 */
export const LEVEL_BG: Record<string, string> = {
  critical: softBg(C.danger, 0.10),
  warning:  softBg(C.warn, 0.10),
  bearish:  softBg(C.down, 0.08),
  bullish:  softBg(C.ok, 0.08),
  neutral:  softBg(C.text2, 0.08),
}

/** 레벨별 테두리색 */
export const LEVEL_BORDER: Record<string, string> = {
  critical: softBg(C.danger, 0.4),
  warning:  softBg(C.warn, 0.3),
  bearish:  softBg(C.down, 0.25),
  bullish:  softBg(C.ok, 0.25),
  neutral:  softBg(C.text2, 0.2),
}
