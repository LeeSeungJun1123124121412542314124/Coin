import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getPerformance, getSettings, putSettings } from '../../lib/learningApi.ts'
import type { PerformanceResponse } from '../../lib/learningApi.ts'
import { C } from '../../lib/theme.ts'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import { SkeletonCard } from '../shared/Skeleton'
import { formatUsdtKrw } from './learningChartData.ts'
import { DIM, MUTED, errorStyle, errorText, fmtRatio, inputStyle, noteStyle, titleStyle, useLoader } from './learningShared.ts'

// 성과 — 국면 판정 적중률(14·28일), 청산 승률, 계좌 자산 vs DCA 기준선
export function PerformancePanel({ symbols }: { symbols: string[] }) {
  const perf = useLoader(getPerformance)
  const settings = useLoader(getSettings)
  const [saving, setSaving] = useState(false)
  const [dcaError, setDcaError] = useState<string | null>(null)

  // DCA 기준 종목 변경 — 추적 종목이 아니면 400
  const changeDca = async (symbol: string) => {
    setSaving(true)
    setDcaError(null)
    try {
      await putSettings({ dca: { symbol } })
      settings.reload()
      perf.reload()
    } catch (e) {
      setDcaError(errorText(e))
    } finally {
      setSaving(false)
    }
  }

  if (perf.error) return <ErrorState error={perf.error} onRetry={perf.reload} />
  if (!perf.data) return <SkeletonCard height={240} />
  const p = perf.data
  const dcaSymbol = settings.data?.dca.symbol ?? p.dca?.symbol ?? ''
  const options = symbols.includes(dcaSymbol) || !dcaSymbol ? symbols : [dcaSymbol, ...symbols]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        {(['14', '28'] as const).map(h => {
          const r = p.hit_rate[h]
          return (
            <Card key={h}>
              <div style={{ color: DIM, fontSize: '0.78rem' }}>{h}일 국면 적중률</div>
              <div style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '1.4rem', fontWeight: 700, margin: '4px 0' }}>{fmtRatio(r?.hit_rate ?? null)}</div>
              <div style={{ color: MUTED, fontSize: '0.75rem' }}>
                {r && r.n > 0 ? `확정 ${r.n}건 · 부분 적중 ${fmtRatio(r.partial_ratio)} 별도` : '확정된 복기가 없습니다'}
              </div>
            </Card>
          )
        })}
        <Card>
          <div style={{ color: DIM, fontSize: '0.78rem' }}>청산 승률</div>
          <div style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '1.4rem', fontWeight: 700, margin: '4px 0' }}>{fmtRatio(p.win_rate.win_rate)}</div>
          <div style={{ color: MUTED, fontSize: '0.75rem' }}>
            {p.win_rate.n > 0 ? `청산 ${p.win_rate.n}건 (실현 손익 > 0이면 승)` : '청산된 포지션이 없습니다'}
          </div>
        </Card>
      </div>

      <Card>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <h3 style={{ ...titleStyle, margin: 0 }}>계좌 자산 vs DCA 기준선</h3>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: MUTED }}>
            DCA 기준 종목
            <select
              style={inputStyle}
              value={dcaSymbol}
              disabled={saving || options.length === 0}
              onChange={e => changeDca(e.target.value)}
            >
              {options.length === 0 && <option value="">추적 종목 없음</option>}
              {options.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        {dcaError && <div style={{ ...errorStyle, marginBottom: 8 }}>{dcaError}</div>}
        {p.dca === null && p.dca_reason && <div style={{ ...noteStyle, marginBottom: 8 }}>DCA 기준선 없음: {p.dca_reason}</div>}
        <LatestValues perf={p} />
        <EquityChart perf={p} />
      </Card>
    </div>
  )
}

function LatestValues({ perf }: { perf: PerformanceResponse }) {
  const equity = perf.equity.at(-1)?.value ?? null
  const dca = perf.dca?.series.at(-1)?.value ?? null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, fontSize: '0.82rem', color: 'var(--text-2)', marginBottom: 10 }}>
      <div><span style={{ color: DIM }}>계좌 자산 </span>{equity === null ? '—' : formatUsdtKrw(equity, perf.usd_krw)}</div>
      {perf.dca && (
        <div><span style={{ color: DIM }}>DCA ({perf.dca.symbol}) </span>{dca === null ? '—' : formatUsdtKrw(dca, perf.usd_krw)}</div>
      )}
      {perf.usd_krw === null && <div style={{ color: MUTED }}>환율을 가져오지 못해 원화 환산을 생략했습니다</div>}
    </div>
  )
}

function EquityChart({ perf }: { perf: PerformanceResponse }) {
  // 날짜 기준으로 두 곡선을 합친다
  const byDate = new Map<string, { date: string; equity?: number; dca?: number }>()
  for (const e of perf.equity) byDate.set(e.date, { date: e.date, equity: e.value })
  for (const d of perf.dca?.series ?? []) byDate.set(d.date, { ...byDate.get(d.date), date: d.date, dca: d.value })
  const rows = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))

  if (rows.length === 0) return <div style={noteStyle}>곡선 데이터가 없습니다.</div>
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={rows}>
        <CartesianGrid stroke={C.line} strokeDasharray="3 3" />
        <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: C.text3, fontSize: 11 }} width={60} domain={['auto', 'auto']} />
        <Tooltip
          contentStyle={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.text }}
          formatter={(v) => (typeof v === 'number' ? `${v.toFixed(2)} USDT` : String(v))}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: C.text2 }} />
        <Line type="monotone" dataKey="equity" name="계좌 자산" stroke={C.accent} dot={false} strokeWidth={2} connectNulls />
        {perf.dca && (
          <Line type="monotone" dataKey="dca" name={`DCA (${perf.dca.symbol})`} stroke={C.info} dot={false} strokeWidth={2} connectNulls />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}
