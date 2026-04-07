import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import { StatRow } from '../shared/StatRow'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Legend, ComposedChart, Bar,
} from 'recharts'

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
  supply: '#4ade80',
  drain: '#f87171',
  neutral: '#94a3b8',
  unknown: '#64748b',
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

  const { data: summary, loading } = useApi<LiquiditySummary>('/api/liquidity-summary', 3_600_000)
  const { data: tgaHistory } = useApi<{ history: TgaPoint[] }>('/api/tga-history', 3_600_000)
  const { data: m2History } = useApi<{ history: M2Point[] }>('/api/m2-history', 3_600_000)
  const { data: treasury } = useApi<TreasuryData>('/api/treasury-auctions', 3_600_000)

  if (loading || !summary) {
    return <div style={{ color: '#64748b', padding: 32, textAlign: 'center' }}>유동성 데이터 로드 중...</div>
  }

  const dirColor = DIRECTION_COLOR[summary.overall_direction] ?? '#94a3b8'
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

      {/* 유동성 방향 배너 */}
      <div style={{
        background: `${dirColor}15`,
        border: `1px solid ${dirColor}50`,
        borderRadius: 10, padding: '12px 16px',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span style={{ fontSize: '1.2rem' }}>
          {summary.overall_direction === 'supply' ? '🟢' : summary.overall_direction === 'drain' ? '🔴' : '⚪'}
        </span>
        <div>
          <div style={{ color: dirColor, fontWeight: 700, fontSize: '0.95rem' }}>
            {dirLabel}
          </div>
          <div style={{ color: '#64748b', fontSize: '0.78rem', marginTop: 2 }}>
            매크로 유동성 환경 — TGA·M2·SOMA 종합 판단
          </div>
        </div>
        {summary.m2.yoy_pct != null && (
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ color: '#94a3b8', fontSize: '0.7rem' }}>M2 YoY</div>
            <div style={{
              color: (summary.m2.yoy_pct ?? 0) > 3 ? '#4ade80' : (summary.m2.yoy_pct ?? 0) < 1 ? '#f87171' : '#f59e0b',
              fontWeight: 700, fontSize: '1.1rem',
            }}>
              {summary.m2.yoy_pct?.toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {/* 요약 카드 3개 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>TGA 잔고</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#e2e8f0' }}>
            ${summary.tga.current_b?.toFixed(0) ?? '—'}B
          </div>
          {summary.tga['7d_change_b'] != null && (
            <div style={{
              color: (summary.tga['7d_change_b'] ?? 0) < 0 ? '#4ade80' : '#f87171',
              fontSize: '0.8rem', marginTop: 4,
            }}>
              {(summary.tga['7d_change_b'] ?? 0) < 0 ? '▼' : '▲'} 주간 {Math.abs(summary.tga['7d_change_b'] ?? 0).toFixed(1)}B
              {(summary.tga['7d_change_b'] ?? 0) < 0 ? ' (유동성 공급)' : ' (유동성 흡수)'}
            </div>
          )}
        </Card>

        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>M2 통화량</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#e2e8f0' }}>
            ${summary.m2.current_b ? (summary.m2.current_b / 1000).toFixed(1) : '—'}T
          </div>
          <div style={{ color: '#64748b', fontSize: '0.78rem', marginTop: 4 }}>
            YoY {summary.m2.yoy_pct?.toFixed(2) ?? '—'}%
          </div>
        </Card>

        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>연준 대차대조표 (SOMA)</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#e2e8f0' }}>
            ${summary.soma.current_b?.toFixed(1) ?? '—'}T
          </div>
          {summary.soma['7d_change_b'] != null && (
            <div style={{
              color: (summary.soma['7d_change_b'] ?? 0) < 0 ? '#f87171' : '#4ade80',
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
            <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
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
                    background: tgaLag === lag ? '#2563eb' : '#1e293b',
                    color: tgaLag === lag ? '#fff' : '#94a3b8',
                  }}
                >
                  {lag}W
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={tgaChart}>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis yAxisId="yoy" orientation="left" tick={{ fill: '#4ade80', fontSize: 10 }} width={30} />
              <YAxis yAxisId="btc" orientation="right" tick={{ fill: '#f59e0b', fontSize: 10 }} width={40} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v: number, name: string) =>
                  name === 'TGA YoY' ? [`${v?.toFixed(1)}%`, name] : [`$${v}K`, name]
                }
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
              <ReferenceLine yAxisId="yoy" y={0} stroke="#334155" />
              <Bar yAxisId="yoy" dataKey="yoy_pct" fill="rgba(74,222,128,0.3)" name="TGA YoY" barSize={6} />
              <Line yAxisId="btc" type="monotone" dataKey="btc" stroke="#f59e0b" dot={false} strokeWidth={2} name="BTC" />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* M2 YoY 차트 */}
      {m2Chart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>M2 YoY 변화율 (3년)</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={m2Chart}>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval={5} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={30} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                formatter={(v: number) => [`${v.toFixed(2)}%`, 'M2 YoY']}
              />
              <ReferenceLine y={3} stroke="#4ade80" strokeDasharray="3 3" label={{ value: '3%', fill: '#4ade80', fontSize: 10 }} />
              <ReferenceLine y={1} stroke="#f87171" strokeDasharray="3 3" label={{ value: '1%', fill: '#f87171', fontSize: 10 }} />
              <Line type="monotone" dataKey="yoy_pct" stroke="#60a5fa" dot={false} strokeWidth={2} name="M2 YoY" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* 국채 경매 일정 */}
      {treasury && (treasury.upcoming.length > 0 || treasury.recent.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {treasury.upcoming.length > 0 && (
            <Card>
              <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>
                향후 국채 경매 ({treasury.upcoming.length}건)
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {treasury.upcoming.slice(0, 8).map((a, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 8px', background: '#0f1117', borderRadius: 6 }}>
                    <span style={{ color: '#64748b', fontSize: '0.75rem', width: 80 }}>{a.auction_date}</span>
                    <span style={{ color: '#cbd5e1', fontSize: '0.78rem' }}>{a.term} {a.type}</span>
                    <span style={{ color: a.offering_amount_b && a.offering_amount_b > 50 ? '#f87171' : '#94a3b8', fontSize: '0.78rem' }}>
                      {a.offering_amount_b != null ? `$${a.offering_amount_b}B` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {treasury.recent.length > 0 && (
            <Card>
              <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>최근 경매 결과</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {treasury.recent.slice(0, 8).map((a, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 8px', background: '#0f1117', borderRadius: 6 }}>
                    <span style={{ color: '#64748b', fontSize: '0.75rem', width: 80 }}>{a.auction_date}</span>
                    <span style={{ color: '#cbd5e1', fontSize: '0.78rem' }}>{a.term}</span>
                    <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                      {a.bid_to_cover != null ? `BTC ${a.bid_to_cover.toFixed(2)}x` : '—'}
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
