import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { IchimokuState, Interval, Phase, Verdict } from '../../lib/learningApi.ts'
import { PHASE_LABELS } from './learningChartData.ts'

// ── 비동기 조회 훅 ──
// load 함수가 바뀌면(호출 측 useCallback/useMemo 의존성 변경) 다시 불러오고, reload()로 같은 대상을 재조회한다.
// effect 본문에서는 setState 하지 않고 Promise 콜백에서만 갱신한다 (react-hooks/set-state-in-effect).
interface LoadState<T> {
  load: () => Promise<T>
  data: T | null
  error: string | null
}

export function useLoader<T>(load: (() => Promise<T>) | null) {
  const [nonce, setNonce] = useState(0)
  const [state, setState] = useState<LoadState<T> | null>(null)

  useEffect(() => {
    if (!load) return
    let cancelled = false
    load().then(
      data => { if (!cancelled) setState({ load, data, error: null }) },
      (e: unknown) => { if (!cancelled) setState({ load, data: null, error: errorText(e) }) },
    )
    return () => { cancelled = true }
  }, [load, nonce])

  const reload = useCallback(() => setNonce(n => n + 1), [])
  // 대상이 바뀌면 이전 결과는 버리고, 같은 대상 재조회 중에는 이전 결과를 유지
  const same = state !== null && state.load === load
  return {
    data: same ? state.data : null,
    error: same ? state.error : null,
    reload,
  }
}

// apiFetch 오류는 "HTTP 400: <detail>" 형태 그대로 보여준다
export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

// ── 표기 ──

export const INTERVAL_LABELS: Record<Interval, string> = { '1d': '일봉', '4h': '4시간봉' }

export const VERDICT_LABELS: Record<Verdict, string> = { hit: '적중', partial: '부분 적중', miss: '빗나감' }

// 일목 상태 4항목 — 값 null은 '판단 불가'
export const ICHIMOKU_FIELDS: { key: keyof IchimokuState; label: string; options: Record<string, string> }[] = [
  { key: 'cloud_position', label: '구름 위치', options: { above: '구름 위', inside: '구름 안', below: '구름 아래' } },
  { key: 'tk_cross', label: '전환·기준선', options: { golden: '골든크로스', dead: '데드크로스', none: '교차 없음' } },
  { key: 'chikou', label: '후행스팬', options: { above: '가격 위', below: '가격 아래' } },
  { key: 'future_cloud', label: '미래 구름', options: { bullish: '양운', bearish: '음운' } },
]

export const UNDECIDABLE = '판단 불가'

export function ichimokuText(state: IchimokuState | null): string {
  if (!state) return `일목 ${UNDECIDABLE}`
  return ICHIMOKU_FIELDS.map(f => {
    const v = state[f.key]
    return `${f.label} ${v === null ? UNDECIDABLE : f.options[v]}`
  }).join(' · ')
}

export function rationaleText(phase: Phase, ichimoku: IchimokuState | null): string {
  return `국면 ${PHASE_LABELS[phase]} · ${ichimokuText(ichimoku)}`
}

const priceFormat = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 8 })
const qtyFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 8 })

export const fmtPrice = (v: number | null) => (v === null ? '—' : priceFormat.format(v))
export const fmtQty = (v: number) => qtyFormat.format(v)
export const fmtRatio = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(1)}%`)
export const fmtSignedPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
export const pnlColor = (v: number | null) => (v === null || v === 0 ? '#94a3b8' : v > 0 ? '#4ade80' : '#f87171')

// 캔들 시각(epoch ms, UTC) — 4시간봉은 시각까지
export function fmtBarTime(ms: number, withHour: boolean): string {
  const iso = new Date(ms).toISOString()
  return withHour ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC` : iso.slice(0, 10)
}

export const fmtDateTime = (iso: string) => new Date(iso).toLocaleString('ko-KR')

// ── 스타일 (기존 화면 색상 체계) ──

export const MUTED = '#94a3b8'
export const DIM = '#64748b'
export const TEXT = '#e2e8f0'

export const titleStyle: CSSProperties = { fontSize: '0.95rem', fontWeight: 700, color: TEXT, margin: '0 0 12px' }
export const errorStyle: CSSProperties = { color: '#f87171', fontSize: '0.8rem' }
export const noteStyle: CSSProperties = { color: MUTED, fontSize: '0.8rem' }

export const inputStyle: CSSProperties = {
  background: '#0f172a',
  border: '1px solid #334155',
  borderRadius: 6,
  color: TEXT,
  padding: '6px 8px',
  fontSize: '0.8rem',
}

export const toggleStyle = (active: boolean): CSSProperties => ({
  background: active ? '#1e3a5f' : 'transparent',
  border: `1px solid ${active ? '#60a5fa' : '#334155'}`,
  borderRadius: 8,
  padding: '6px 14px',
  fontSize: 13,
  color: active ? '#60a5fa' : DIM,
  cursor: 'pointer',
  fontWeight: active ? 600 : 400,
})

export const buttonStyle = (enabled: boolean): CSSProperties => ({
  background: enabled ? '#2563eb' : '#334155',
  border: 'none',
  borderRadius: 6,
  padding: '6px 14px',
  fontSize: '0.8rem',
  color: enabled ? '#fff' : DIM,
  cursor: enabled ? 'pointer' : 'not-allowed',
  fontWeight: 600,
})

export const thStyle: CSSProperties = { padding: '6px', fontWeight: 500 }
export const tdStyle: CSSProperties = { padding: '6px', color: '#cbd5e1' }
