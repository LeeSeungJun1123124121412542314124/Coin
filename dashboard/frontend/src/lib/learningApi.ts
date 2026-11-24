import { apiFetch } from './api.ts'

// ── 응답 타입 (백엔드 learning_* 서비스 기준, 시각은 epoch ms) ──

export type Interval = '1h' | '4h' | '1d' | '1w' | '1M'
export type Phase = 'accumulation' | 'markup' | 'distribution' | 'markdown' | 'unclear'

export interface LearningSymbol {
  symbol: string
  listed_at: string | null
  added_at: string
  backfill_status: string
}

export interface LearningSettings {
  wyckoff: { n: number; width_pct: number; vol_mult: number }
  elliott: {
    threshold_1h: number; threshold_4h: number; threshold_1d: number
    threshold_1w: number; threshold_1M: number; levels: number[]
  }
  dca: { symbol: string }
  indicators: {
    ma: { enabled: boolean; type: 'sma' | 'ema'; periods: number[] }
    bb: { enabled: boolean; period: number; stddev: number }
    volume: { enabled: boolean }
    rsi: { enabled: boolean; period: number }
    macd: { enabled: boolean; fast: number; slow: number; signal: number }
  }
}

export interface Candle {
  open_time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface IchimokuRow {
  time: number
  tenkan: number | null
  kijun: number | null
  senkou_a: number | null
  senkou_b: number | null
  chikou: number | null
}

export type IchimokuLineKey = 'tenkan' | 'kijun' | 'senkou_a' | 'senkou_b' | 'chikou'

// 판단 불가는 null (Ruling R5)
export interface IchimokuState {
  cloud_position: 'above' | 'inside' | 'below' | null
  tk_cross: 'golden' | 'dead' | 'none' | null
  chikou: 'above' | 'below' | null
  future_cloud: 'bullish' | 'bearish' | null
}

export interface WyckoffCandidate {
  time: number
  type: 'spring' | 'upthrust'
  strong: boolean
  box_high: number
  box_low: number
}

export interface WyckoffBox {
  high: number
  low: number
  start: number
  end: number
}

export interface Wyckoff {
  volume_spikes: number[]
  candidates: WyckoffCandidate[]
  current_box: WyckoffBox | null
}

export interface Pivot {
  time: number
  price: number
  kind: 'high' | 'low'
}

export interface FibLevel {
  level: number
  price: number
}

// 켜진 지표만 존재 (거래량은 캔들의 volume 사용)
export interface IndicatorsResponse {
  ma?: { period: number; points: { time: number; value: number }[] }[]
  bb?: { time: number; upper: number; mid: number; lower: number }[]
  rsi?: { time: number; value: number }[]
  macd?: { time: number; macd: number; signal: number; hist: number }[]
}

// ── 구조 점수 (HTF-LTF) ──

export interface StructureBreak {
  time: number
  level: number
  direction: 'up' | 'down'
  kind: 'bos' | 'choch'
  strength: 'weak' | 'strong'
  bars_ago: number
}

export interface StructureTimeframe {
  trend: 'up' | 'down' | 'neutral'
  fresh: boolean
  insufficient: boolean
  last_break: StructureBreak | null
  range: { high: number | null; low: number | null }
}

export interface Structure {
  htf_interval: '1d' | '1w' | '1M' | null
  htf: StructureTimeframe
  ltf: StructureTimeframe
  score: number
  label: 'bullish' | 'neutral' | 'bearish'
  reasons: string[]
  htf_pts: number
  ltf_pts: number
  bonus: number
}

export interface ChartResponse {
  candles: Candle[]
  ichimoku: IchimokuRow[]
  wyckoff: Wyckoff
  pivots: Pivot[]
  fib: FibLevel[]
  state: IchimokuState
  settings: LearningSettings
  indicators?: IndicatorsResponse
  structure: Structure | null
}

export interface OrderContext {
  ichimoku_state: IchimokuState
  wyckoff_recent: WyckoffCandidate[]
  current_box: WyckoffBox | null
}

export interface AccountPosition {
  symbol: string
  qty: number
  avg_cost: number
  market_value: number | null
  unrealized_pnl: number | null
}

export interface AccountResponse {
  started_at: string
  initial_usdt: number
  cash_usdt: number
  positions: AccountPosition[]
  equity_usdt: number | null
  equity_krw: number | null
  usd_krw: number | null
}

export interface OrderRationale {
  phase: Phase
  ichimoku: IchimokuState
  memo?: string
}

export interface OrderBody {
  symbol: string
  side: 'buy' | 'sell'
  usdt_amount?: number
  qty?: number
  rationale: OrderRationale
  interval?: Interval
}

export interface OrderResult {
  fill_id: number
  position_id: number
  qty: number
  price: number
  fee_usdt: number
  cash_usdt: number
}

export interface JournalFill {
  id: number
  position_id: number
  symbol: string
  side: 'buy' | 'sell'
  qty: number
  price: number
  usdt_amount: number
  fee_usdt: number
  executed_at: string
  phase: Phase
  memo: string | null
  ichimoku: IchimokuState | null
  detected: OrderContext | null
  snapshot: Record<string, unknown> | null
}

export interface JournalPosition {
  id: number
  symbol: string
  opened_at: string
  entry_phase: Phase
  first_entry_price: number
  status: 'open' | 'closed'
  closed_at: string | null
}

export interface JournalEntry {
  position: JournalPosition
  fills: JournalFill[]
}

export type Verdict = 'hit' | 'partial' | 'miss'

export interface ReviewPending {
  status: 'pending'
  due: string
}

export interface ReviewReady {
  status: 'ready'
  rationale: { phase: Phase; ichimoku: IchimokuState | null; detected: OrderContext | null; memo: string | null }
  close_price: number
  pnl_usdt: number
  hold_return_pct: number
  suggested: Verdict | null
  confirmed: Verdict | null
  reason: string | null
}

export type Review = ReviewPending | ReviewReady

// 키는 복기 기간(일): "14", "28"
export type ReviewsResponse = Record<string, Review>

export interface ConfirmedReview {
  suggested: Verdict | null
  confirmed: Verdict | null
  reason: string | null
  close_price: number
}

export interface PerformanceResponse {
  hit_rate: Record<string, { n: number; hit_rate: number | null; partial_ratio: number | null }>
  win_rate: { n: number; win_rate: number | null }
  equity: { date: string; value: number }[]
  dca: { symbol: string; series: { date: string; value: number }[] } | null
  dca_reason: string | null
  usd_krw: number | null
}

// ── API 호출 ──

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getSymbols = () => apiFetch<LearningSymbol[]>('/api/learning/symbols')

export const addSymbol = (symbol: string) =>
  apiFetch<LearningSymbol>('/api/learning/symbols', jsonBody('POST', { symbol }))

export const removeSymbol = (symbol: string) =>
  apiFetch<{ removed: string }>(`/api/learning/symbols/${encodeURIComponent(symbol)}`, { method: 'DELETE' })

export const getSettings = () => apiFetch<LearningSettings>('/api/learning/settings')

// indicators는 서버가 깊은 병합하므로 하위 지표도 부분 객체를 허용한다
type SettingsPatch = Omit<{ [K in keyof LearningSettings]?: Partial<LearningSettings[K]> }, 'indicators'> & {
  indicators?: { [K in keyof LearningSettings['indicators']]?: Partial<LearningSettings['indicators'][K]> }
}

export const putSettings = (patch: SettingsPatch) =>
  apiFetch<LearningSettings>('/api/learning/settings', jsonBody('PUT', patch))

export const getChart = (symbol: string, interval: Interval, limit?: number) => {
  const q = new URLSearchParams({ symbol, interval })
  if (limit !== undefined) q.set('limit', String(limit))
  return apiFetch<ChartResponse>(`/api/learning/chart?${q}`)
}

export const getOrderContext = (symbol: string, interval: Interval) =>
  apiFetch<OrderContext>(`/api/learning/order-context?${new URLSearchParams({ symbol, interval })}`)

export const getAccount = () => apiFetch<AccountResponse>('/api/learning/account')

export const postOrder = (body: OrderBody) => apiFetch<OrderResult>('/api/learning/orders', jsonBody('POST', body))

export const getJournal = () => apiFetch<JournalEntry[]>('/api/learning/journal')

export const getReviews = (positionId: number) =>
  apiFetch<ReviewsResponse>(`/api/learning/reviews/${positionId}`)

export const confirmReview = (positionId: number, horizon: number, verdict: Verdict, reason: string) =>
  apiFetch<ConfirmedReview>(
    `/api/learning/reviews/${positionId}/${horizon}/confirm`,
    jsonBody('POST', { verdict, reason }),
  )

export const getPerformance = () => apiFetch<PerformanceResponse>('/api/learning/performance')
