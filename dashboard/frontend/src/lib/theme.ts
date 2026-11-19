/** 디자인 토큰 hex 값 (src/index.css :root 변수와 같은 값 — recharts·lightweight-charts용) */
export const C = {
  bg: '#09090B',
  bgInset: '#0D0D10',
  surface: '#131316',
  surface2: '#19191D',
  border: '#222227',
  line: '#1C1C21',
  segActive: '#2B2B31',
  borderStrong: '#313138',
  text: '#F1F1F3',
  text2: '#ABABB4',
  text3: '#86868F',
  accent: '#C8A86B',
  up: '#F2606A',
  down: '#5AA9FF',
  warn: '#E8913A',
  warnText: '#F0A35E',
  ok: '#3FCB8B',
  danger: '#FF7A5C',
  violet: '#B58CFF',
  info: '#8EA2FF',
  neutralSeries: '#6E6E78',
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

/** 레벨별 텍스트 색상 */
export const LEVEL_COLORS: Record<string, string> = {
  critical: C.danger,
  warning:  C.warn,
  bearish:  C.down,
  bullish:  C.up,
  neutral:  C.text2,
}

/** 레벨별 배경색 */
export const LEVEL_BG: Record<string, string> = {
  critical: softBg(C.danger, 0.10),
  warning:  softBg(C.warn, 0.10),
  bearish:  softBg(C.down, 0.08),
  bullish:  softBg(C.up, 0.08),
  neutral:  softBg(C.text2, 0.08),
}

/** 레벨별 테두리색 */
export const LEVEL_BORDER: Record<string, string> = {
  critical: softBg(C.danger, 0.4),
  warning:  softBg(C.warn, 0.3),
  bearish:  softBg(C.down, 0.25),
  bullish:  softBg(C.up, 0.25),
  neutral:  softBg(C.text2, 0.2),
}
