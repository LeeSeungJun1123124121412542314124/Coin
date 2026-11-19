// 대시보드 "BTC 시장 국면" 카드용 데이터 가공 (순수 함수)
import type { ChartResponse } from '../../lib/learningApi.ts'
import { ICHIMOKU_FIELDS, UNDECIDABLE } from '../learning/learningShared.ts'

export type PhaseTone = 'up' | 'down' | 'flat'

export interface BtcPhase {
  close: number
  changePct: number
  low: number
  high: number
  spark: string
  states: { k: string; v: string; tone: PhaseTone }[]
}

const SPARK_W = 300
const SPARK_H = 64
const SPARK_PAD = 4

// 일목 상태값 → 색 방향
const TONES: Record<string, PhaseTone> = {
  above: 'up', below: 'down', inside: 'flat',
  golden: 'up', dead: 'down', none: 'flat',
  bullish: 'up', bearish: 'down',
}

export function summarizeBtcPhase(res: ChartResponse | null): BtcPhase | null {
  const candles = res?.candles
  if (!res || !candles || candles.length < 2) return null

  const last = candles[candles.length - 1]
  const prev = candles[candles.length - 2]
  const changePct = Math.round(((last.close / prev.close - 1) * 100) * 100) / 100

  const closes = candles.map(c => c.close)
  const min = Math.min(...closes)
  const max = Math.max(...closes)
  const span = max - min || 1
  const spark = closes
    .map((v, i) => {
      const x = (i / (closes.length - 1)) * SPARK_W
      const y = SPARK_PAD + (1 - (v - min) / span) * (SPARK_H - SPARK_PAD * 2)
      return `${+x.toFixed(1)},${+y.toFixed(1)}`
    })
    .join(' ')

  const states = ICHIMOKU_FIELDS.map(f => {
    const raw = res.state?.[f.key] ?? null
    return raw === null
      ? { k: f.label, v: UNDECIDABLE, tone: 'flat' as PhaseTone }
      : { k: f.label, v: f.options[raw], tone: TONES[raw] ?? 'flat' }
  })

  return {
    close: last.close,
    changePct,
    low: Math.min(...candles.map(c => c.low)),
    high: Math.max(...candles.map(c => c.high)),
    spark,
    states,
  }
}
