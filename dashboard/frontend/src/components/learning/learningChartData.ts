import type { SeriesMarker, UTCTimestamp } from 'lightweight-charts'
import type { Candle, IchimokuLineKey, IchimokuRow, Phase, Pivot, Wyckoff } from '../../lib/learningApi.ts'
import { C } from '../../lib/theme.ts'

// 와이코프 국면 한국어 표기
export const PHASE_LABELS: Record<Phase, string> = {
  accumulation: '매집',
  markup: '상승',
  distribution: '분산',
  markdown: '하락',
  unclear: '불명확',
}

const SPRING_COLOR = C.up
const UPTHRUST_COLOR = C.down

// 백엔드 epoch ms -> lightweight-charts 초 단위 시각
export const toSec = (ms: number) => Math.floor(ms / 1000) as UTCTimestamp

export function toCandleSeries(candles: Candle[]) {
  return candles.map(c => ({ time: toSec(c.open_time), open: c.open, high: c.high, low: c.low, close: c.close }))
}

export function toLineSeries(ich: IchimokuRow[], key: IchimokuLineKey) {
  const out: { time: UTCTimestamp; value: number }[] = []
  for (const r of ich) {
    const v = r[key]
    if (v !== null) out.push({ time: toSec(r.time), value: v })
  }
  return out
}

// 선행스팬 A·B가 모두 있는 행만 구름 구간으로 사용
export function toCloudBands(ich: IchimokuRow[]) {
  const out: { time: UTCTimestamp; top: number; bottom: number; bullish: boolean }[] = []
  for (const r of ich) {
    const a = r.senkou_a
    const b = r.senkou_b
    if (a === null || b === null) continue
    out.push({ time: toSec(r.time), top: Math.max(a, b), bottom: Math.min(a, b), bullish: a > b })
  }
  return out
}

export function toWyckoffMarkers(wyckoff: Wyckoff): SeriesMarker<UTCTimestamp>[] {
  return wyckoff.candidates
    .map((c): SeriesMarker<UTCTimestamp> => {
      const prefix = c.strong ? '강 ' : ''
      return c.type === 'spring'
        ? { time: toSec(c.time), position: 'belowBar', shape: 'arrowUp', color: SPRING_COLOR, text: `${prefix}스프링` }
        : { time: toSec(c.time), position: 'aboveBar', shape: 'arrowDown', color: UPTHRUST_COLOR, text: `${prefix}업스러스트` }
    })
    .sort((x, y) => x.time - y.time)
}

export function toPivotLine(pivots: Pivot[]) {
  return pivots.map(p => ({ time: toSec(p.time), value: p.price })).sort((x, y) => x.time - y.time)
}

const numberFormat = (digits: number) =>
  new Intl.NumberFormat('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export function formatUsdtKrw(usdt: number, rate: number | null): string {
  const base = `${numberFormat(2).format(usdt)} USDT`
  if (rate === null) return base
  return `${base} (≈ ${numberFormat(0).format(Math.round(usdt * rate))}원)`
}
