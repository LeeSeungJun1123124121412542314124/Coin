/**
 * 숫자를 읽기 쉬운 형식으로 포맷
 * @param v - 값 (null/undefined이면 '—' 반환)
 * @param decimals - 소수점 자릿수 (기본 2)
 *
 * 변환 기준:
 *   ≥ 1T  → $X.XXT
 *   ≥ 1B  → $X.XXB
 *   ≥ 1M  → $X.XXM
 *   ≥ 1K  → $X.XXK
 *   그 외  → $X.XX
 */
export function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(decimals)}T`
  if (abs >= 1e9)  return `$${(v / 1e9).toFixed(decimals)}B`
  if (abs >= 1e6)  return `$${(v / 1e6).toFixed(decimals)}M`
  if (abs >= 1e3)  return `$${(v / 1e3).toFixed(decimals)}K`
  return `$${v.toFixed(decimals)}`
}

/** 천 단위 쉼표와 정확히 digits 자리 소수. null/undefined이면 '—' */
export function fmtFixed(v: number | null | undefined, digits: number): string {
  if (v == null || !Number.isFinite(v)) return '—'
  // 반올림하면 0이 되는 값은 부호 없이 표시
  const n = Number(v.toFixed(digits)) === 0 ? 0 : v
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** 부호 붙은 퍼센트: +1.30% / −2.27%(U+2212) / 0.00% */
export function fmtSignedPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const body = `${fmtFixed(Math.abs(v), digits)}%`
  if (Number(Math.abs(v).toFixed(digits)) === 0) return body
  return `${v > 0 ? '+' : '−'}${body}`
}

/** 지수: 소수 2자리 고정 */
export function fmtIndex(v: number | null | undefined): string {
  return fmtFixed(v, 2)
}

/** 코인 달러 가격: 1000 이상 0자리, 1 이상 2자리, 1 미만 3자리 */
export function fmtCoinPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  const digits = abs >= 1000 ? 0 : abs >= 1 ? 2 : 3
  return `$${fmtFixed(v, digits)}`
}
