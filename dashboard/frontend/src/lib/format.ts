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
