import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Legend, ComposedChart,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { C, changeColor, softBg } from '../../lib/theme'

interface LiquiditySummary {
  tga: { current_b: number | null; '7d_change_b': number | null; direction: string }
  m2: { current_b: number | null; yoy_pct: number | null }
  soma: { current_b: number | null; '7d_change_b': number | null }
  overall_direction: string
}

interface TgaPoint {
  date: string
  tga_b: number
  yoy_pct: number
  btc: number | null
}

interface M2Point {
  date: string
  value: number
  yoy_pct: number
}

interface AuctionItem {
  auction_date: string
  type: string
  term: string
  offering_amount_b: number | null
  bid_to_cover?: number | null
}

interface TreasuryData {
  upcoming: AuctionItem[]
  recent: AuctionItem[]
}

const DIRECTION_COLOR: Record<string, string> = {
  supply: C.ok,
  drain: C.warn,
  neutral: C.text2,
  unknown: C.text3,
}

const DIRECTION_LABEL: Record<string, string> = {
  supply: '유동성 공급',
  drain: '유동성 흡수',
  neutral: '중립',
  unknown: '알 수 없음',
}

type TgaLag = 0 | 4 | 8 | 12

export function Liquidity() {
  const [tgaLag, setTgaLag] = useState<TgaLag>(8)

  const { data: summary, loading, error, refetch, lastUpdated } = useApi<LiquiditySummary>('/api/liquidity-summary', 3_600_000)
  const { data: tgaHistory } = useApi<{ history: TgaPoint[] }>('/api/tga-history', 3_600_000)
  const { data: m2History } = useApi<{ history: M2Point[] }>('/api/m2-history', 3_600_000)
  const { data: treasury } = useApi<TreasuryData>('/api/treasury-auctions', 3_600_000)

  if (error && !summary) return <ErrorState error={error} onRetry={refetch} />
  if (loading || !summary) return <Skeleton />

  const dirColor = DIRECTION_COLOR[summary.overall_direction] ?? C.text2
  const dirLabel = DIRECTION_LABEL[summary.overall_direction] ?? '알 수 없음'

  // TGA + BTC (시간 래그 적용)
  const tgaRaw = tgaHistory?.history ?? []
  const tgaChart = tgaRaw.slice(tgaLag).map((row, i) => ({
    date: row.date?.slice(5),
    tga_b: row.tga_b,
    yoy_pct: row.yoy_pct,
    btc: tgaRaw[i]?.btc ? Math.round(tgaRaw[i].btc! / 1000) : null,
  })).slice(-52)

  // M2 YoY 차트
  const m2Chart = (m2History?.history ?? []).slice(-36).map(r => ({
    date: r.date?.slice(0, 7),
    yoy_pct: r.yoy_pct,
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} />
      {/* 유동성 방향 배너 */}
      <div style={{
        background: softBg(dirColor, 0.07),
        border: `1px solid ${softBg(dirColor, 0.28)}`,
        borderRadius: 16, padding: '14px 20px',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span style={{ fontSize: '1.2rem' }}>
          {summary.overall_direction === 'supply' ? '🟢' : summary.overall_direction === 'drain' ? '🔴' : '⚪'}
        </span>
        <div>
          <div style={{ color: dirColor, fontWeight: 700, fontSize: '0.95rem' }}>
            {dirLabel}
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: '0.78rem', marginTop: 2 }}>
            매크로 유동성 환경 — TGA·M2·SOMA 종합 판단
          </div>
        </div>
        {summary.m2.yoy_pct != null && (
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ color: 'var(--text-2)', fontSize: '0.7rem' }}>M2 YoY</div>
            <div style={{
              color: (summary.m2.yoy_pct ?? 0) > 3 ? 'var(--ok)' : (summary.m2.yoy_pct ?? 0) < 1 ? 'var(--warn)' : 'var(--text-2)',
              fontWeight: 700, fontSize: '1.1rem', fontFamily: 'var(--font-mono)',
            }}>
              {summary.m2.yoy_pct?.toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {/* 요약 카드 3개 */}
      <div className="grid-3" style={{ gap: 12 }}>
        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 8 }}>TGA 잔고</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
            ${summary.tga.current_b?.toFixed(0) ?? '—'}B
          </div>
          {summary.tga['7d_change_b'] != null && (
            <div style={{
              color: (summary.tga['7d_change_b'] ?? 0) < 0 ? 'var(--ok)' : 'var(--warn)',
              fontSize: '0.8rem', marginTop: 4,
            }}>
              {(summary.tga['7d_change_b'] ?? 0) < 0 ? '▼' : '▲'} 주간 {Math.abs(summary.tga['7d_change_b'] ?? 0).toFixed(1)}B
              {(summary.tga['7d_change_b'] ?? 0) < 0 ? ' (유동성 공급)' : ' (유동성 흡수)'}
            </div>
          )}
        </Card>

        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 8 }}>M2 통화량</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
            ${summary.m2.current_b ? (summary.m2.current_b / 1000).toFixed(1) : '—'}T
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: '0.78rem', marginTop: 4 }}>
            YoY {summary.m2.yoy_pct?.toFixed(2) ?? '—'}%
          </div>
        </Card>

        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 8 }}>연준 대차대조표 (SOMA)</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
            ${summary.soma.current_b?.toFixed(1) ?? '—'}T
          </div>
          {summary.soma['7d_change_b'] != null && (
            <div style={{
              color: changeColor(summary.soma['7d_change_b']),
              fontSize: '0.78rem', marginTop: 4,
            }}>
              {(summary.soma['7d_change_b'] ?? 0) < 0 ? '▼ QT' : '▲ QE'} {Math.abs(summary.soma['7d_change_b'] ?? 0).toFixed(1)}B/주
            </div>
          )}
        </Card>
      </div>

      {/* TGA vs BTC 차트 (래그 슬라이더) */}
      {tgaChart.length > 0 && (
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ color: 'var(--text-2)', fontSize: '0.75rem' }}>
              TGA YoY vs BTC (BTC: K 단위, 시간 래그 {tgaLag}주)
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {([0, 4, 8, 12] as TgaLag[]).map(lag => (
                <button
                  key={lag}
                  onClick={() => setTgaLag(lag)}
                  style={{
                    padding: '3px 10px', borderRadius: 6, border: 'none', cursor: 'pointer',
                    fontSize: '0.72rem',
                    background: tgaLag === lag ? 'var(--seg-active)' : 'var(--bg-inset)',
                    color: tgaLag === lag ? 'var(--text)' : 'var(--text-2)',
                  }}
                >
                  {lag}W
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={tgaChart}>
              <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis yAxisId="yoy" orientation="left" tick={{ fill: C.ok, fontSize: 10 }} width={30} />
              <YAxis yAxisId="btc" orientation="right" tick={{ fill: C.accent, fontSize: 10 }} width={40} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                labelStyle={{ color: C.text2 }}
                formatter={(v, name) => {
                  const n = v as number
                  return name === 'TGA YoY' ? [`${n?.toFixed(1)}%`, name] : [`$${n}K`, name]
                }}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
              <ReferenceLine yAxisId="yoy" y={0} stroke={C.border} />
              <Line yAxisId="yoy" type="monotone" dataKey="yoy_pct" stroke={C.ok} dot={false} strokeWidth={2} name="TGA YoY" />
              <Line yAxisId="btc" type="monotone" dataKey="btc" stroke={C.accent} dot={false} strokeWidth={2} name="BTC" />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* M2 YoY 차트 */}
      {m2Chart.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>M2 YoY 변화율 (3년)</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={m2Chart}>
              <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 9 }} interval={5} />
              <YAxis tick={{ fill: C.text3, fontSize: 10 }} width={30} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                formatter={(v) => [`${(v as number).toFixed(2)}%`, 'M2 YoY']}
              />
              <ReferenceLine y={3} stroke={C.ok} strokeDasharray="3 3" label={{ value: '3%', fill: C.ok, fontSize: 10 }} />
              <ReferenceLine y={1} stroke={C.warn} strokeDasharray="3 3" label={{ value: '1%', fill: C.warn, fontSize: 10 }} />
              <Line type="monotone" dataKey="yoy_pct" stroke={C.info} dot={false} strokeWidth={2} name="M2 YoY" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* 국채 경매 일정 */}
      {treasury && (treasury.upcoming.length > 0 || treasury.recent.length > 0) && (
        <div className="grid-2" style={{ gap: 12 }}>
          {treasury.upcoming.length > 0 && (
            <Card>
              <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 10 }}>
                향후 국채 경매 ({treasury.upcoming.length}건)
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {treasury.upcoming.slice(0, 8).map((a, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 8px', background: 'var(--bg-inset)', borderRadius: 6 }}>
                    <span style={{ color: 'var(--text-3)', fontSize: '0.75rem', width: 80 }}>{a.auction_date}</span>
                    <span style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>{a.term} {a.type}</span>
                    <span style={{ color: a.offering_amount_b && a.offering_amount_b > 50 ? 'var(--warn)' : 'var(--text-2)', fontSize: '0.78rem' }}>
                      {a.offering_amount_b != null ? `$${a.offering_amount_b}B` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {treasury.recent.length > 0 && (
            <Card>
              <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 10 }}>최근 경매 결과</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {treasury.recent.slice(0, 8).map((a, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 8px', background: 'var(--bg-inset)', borderRadius: 6 }}>
                    <span style={{ color: 'var(--text-3)', fontSize: '0.75rem', width: 80 }}>{a.auction_date}</span>
                    <span style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>{a.term}</span>
                    <span style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>
                      {a.bid_to_cover != null ? `응찰률 ${a.bid_to_cover.toFixed(2)}x` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

    </div>
  )
}
