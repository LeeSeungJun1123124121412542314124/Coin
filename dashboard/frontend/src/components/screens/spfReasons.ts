// SPF 예측 근거 문자열 해석 — "<팩터 이름> <부호 있는 수>"를 쉬운 한국어로 바꾼다.
// 값은 요인 자체가 아니라 "상승 쪽 +, 하락 쪽 −"로 부호를 맞춘 점수라서, 이름에는 방향을 암시하는 말을 넣지 않는다.
// 팩터 이름은 crypto-volatility-bot/app/macro/direction_composite.py의 FACTORS(9개)와
// build_factors의 tga_13w에서 가져왔다.

import { fmtFixed } from '../../lib/format.ts'

export interface ParsedReason {
  label: string
  tone: 'up' | 'down' | 'flat'
  value: string | null
}

const FACTOR_LABELS: Record<string, string> = {
  net_liquidity_13w: '순유동성 13주 변화',
  dxy_13w: '달러지수 13주 변화',
  ust10y_13w: '미국 10년물 금리 13주 변화',
  vix_level: 'VIX 수준',
  mvrv_level: 'MVRV(시장가치 ÷ 실현가치)',
  active_addr_13w: '활성 주소 13주 변화',
  rsi14: 'RSI(14)',
  sma50_dist: '50일 이동평균 이격',
  momentum_30d: '30일 가격 변화',
  tga_13w: '미 재무부 계좌(TGA) 13주 변화',
}

// 이름 + 공백 + 부호(+/-)가 붙은 수 하나로 끝나는 문자열만 대상
const FACTOR_PATTERN = /^([A-Za-z_][A-Za-z0-9_]*)\s+([+-]\d+(?:\.\d+)?)$/

export function parseReason(raw: string): ParsedReason {
  const m = FACTOR_PATTERN.exec(raw)
  if (!m) return { label: raw, tone: 'flat', value: null }
  const [, name, num] = m
  const n = Number(num)
  const label = FACTOR_LABELS[name] ?? name
  if (n === 0) return { label, tone: 'flat', value: num.slice(1) }
  // 음수는 fmtFixed가 U+2212로 표시(원문 소수 자릿수 유지)
  const digits = num.split('.')[1]?.length ?? 0
  return { label, tone: n > 0 ? 'up' : 'down', value: n > 0 ? num : fmtFixed(n, digits) }
}
