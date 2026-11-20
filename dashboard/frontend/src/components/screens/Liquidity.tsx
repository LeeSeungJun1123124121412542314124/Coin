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
import { C, softBg } from '../../lib/theme'
import { fmtFixed, fmtSignedPct } from '../../lib/format'

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
  // 세 값이 모두 비어 있으면 값 카드 대신 안내 카드를 보여 준다
  const noValues = summary.tga.current_b == null && summary.m2.current_b == null && summary.soma.current_b == null

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
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      {/* 유동성 판정 — 맨 위 */}
      <section aria-label="유동성 판정" style={{
        background: softBg(dirColor, 0.07),
        border: `1px solid ${softBg(dirColor, 0.28)}`,
        borderRadius: 16, padding: 16,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
          <span aria-hidden="true" style={{ width: 12, height: 12, borderRadius: '50%', background: dirColor, flexShrink: 0 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ color: 'var(--text-2)', fontSize: 12 }}>매크로 유동성 판정</span>
            <span style={{ color: dirColor, fontWeight: 700, fontSize: 22, letterSpacing: '-0.02em' }}>{dirLabel}</span>
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>TGA · M2 · SOMA 종합</span>
          </div>
        </div>
        {summary.m2.yoy_pct != null && (
          <div style={{ flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>M2 YoY</span>
            <span className="v2-nowrap" style={{
              color: summary.m2.yoy_pct > 3 ? 'var(--ok)' : summary.m2.yoy_pct < 1 ? 'var(--warn)' : 'var(--text-2)',
              fontWeight: 600, fontSize: 26, fontFamily: 'var(--font-mono)',
            }}>
              {fmtSignedPct(summary.m2.yoy_pct)}
            </span>
          </div>
        )}
      </section>

      {/* 요약 카드 3개 — 값이 전부 없으면 안내 카드 하나 */}
      {noValues ? (
        <Card>
          <div role="alert" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '12px 0 4px', textAlign: 'center' }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--warn)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l9 16H3zM12 10v4M12 17h.01" /></svg>
            <span style={{ color: 'var(--text)', fontSize: 16, fontWeight: 600 }}>유동성 데이터를 받지 못했습니다</span>
          </div>
          <button
            type="button"
            onClick={refetch}
            style={{
              width: '100%', minHeight: 44, marginTop: 12, borderRadius: 12,
              border: '1px solid var(--border-strong)', background: 'var(--surface-2)', color: 'var(--text)',
              font: 'inherit', fontSize: 15, fontWeight: 600, cursor: 'pointer',
            }}
          >
            다시 시도
          </button>
        </Card>
      ) : (
        <div className="grid-3" style={{ gap: 12 }}>
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
              <span style={{ color: 'var(--text-2)', fontSize: 14, fontWeight: 600 }}>TGA 잔고</span>
              {summary.tga['7d_change_b'] != null && (
                <span className="v2-nowrap" style={{ fontSize: 12, fontWeight: 600, color: summary.tga.direction === 'supply' ? 'var(--ok)' : 'var(--warn)' }}>
                  {DIRECTION_LABEL[summary.tga.direction] ?? ''}
                </span>
              )}
            </div>
            <div className="v2-nowrap" style={{ fontSize: 28, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
              {summary.tga.current_b != null ? `$${fmtFixed(summary.tga.current_b, 0)}B` : '—'}
            </div>
            {summary.tga['7d_change_b'] != null && (
              <div className="v2-nowrap" style={{
                color: summary.tga['7d_change_b'] < 0 ? 'var(--ok)' : 'var(--warn)',
                fontSize: 14, marginTop: 4, fontFamily: 'var(--font-mono)',
              }}>
                {summary.tga['7d_change_b'] < 0 ? '▼' : '▲'} 주간 {fmtFixed(Math.abs(summary.tga['7d_change_b']), 1)}B
              </div>
            )}
          </Card>

          <Card>
            <div style={{ color: 'var(--text-2)', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>M2 통화량</div>
            <div className="v2-nowrap" style={{ fontSize: 28, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
              {summary.m2.current_b != null ? `$${fmtFixed(summary.m2.current_b / 1000, 1)}T` : '—'}
            </div>
            <div className="v2-nowrap" style={{ color: 'var(--text-3)', fontSize: 14, marginTop: 4, fontFamily: 'var(--font-mono)' }}>
              YoY {summary.m2.yoy_pct != null ? fmtSignedPct(summary.m2.yoy_pct) : '—'}
            </div>
          </Card>

          <Card>
            <div style={{ color: 'var(--text-2)', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>연준 대차대조표 (SOMA)</div>
            <div className="v2-nowrap" style={{ fontSize: 28, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
              {summary.soma.current_b != null ? `$${fmtFixed(summary.soma.current_b, 1)}T` : '—'}
            </div>
            {summary.soma['7d_change_b'] != null && (
              <div className="v2-nowrap" style={{
                color: summary.soma['7d_change_b'] < 0 ? 'var(--warn)' : 'var(--ok)',
                fontSize: 14, marginTop: 4, fontFamily: 'var(--font-mono)',
              }}>
                {summary.soma['7d_change_b'] < 0 ? '▼ QT' : '▲ QE'} {/* soma['7d_change_b']는 이름과 달리 조(T) 단위 — 십억 단위로 환산 */}
                {fmtFixed(Math.abs(summary.soma['7d_change_b']) * 1000, 0)}B/주
              </div>
            )}
          </Card>
        </div>
      )}

      {/* TGA vs BTC 차트 (래그 슬라이더) */}
      {tgaChart.length > 0 && (
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            <div style={{ color: 'var(--text-2)', fontSize: '0.75rem' }}>
              TGA YoY vs BTC (BTC: K 단위, 시간 래그 {tgaLag}주)
            </div>
            <div className="v2-seg" role="group" aria-label="시간 래그">
              {([0, 4, 8, 12] as TgaLag[]).map(lag => (
                <button
                  key={lag}
                  type="button"
                  className="v2-seg-btn"
                  aria-pressed={tgaLag === lag}
                  onClick={() => setTgaLag(lag)}
                >
                  {lag}W
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={tgaChart}>
              <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis yAxisId="yoy" orientation="left" tick={{ fill: C.ok, fontSize: 11 }} width={36} />
              <YAxis yAxisId="btc" orientation="right" tick={{ fill: C.accent, fontSize: 11 }} width={44} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                labelStyle={{ color: C.text2 }}
                formatter={(v, name) => {
                  const n = v as number
                  return name === 'TGA YoY' ? [fmtSignedPct(n, 1), name] : [`$${fmtFixed(n, 0)}K`, name]
                }}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
              <ReferenceLine yAxisId="yoy" y={0} stroke={C.borderStrong} />
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
              <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval={5} />
              <YAxis tick={{ fill: C.text3, fontSize: 11 }} width={36} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                formatter={(v) => [`${fmtFixed(v as number, 2)}%`, 'M2 YoY']}
              />
              <ReferenceLine y={3} stroke={C.ok} strokeDasharray="3 3" label={{ value: '3%', fill: C.ok, fontSize: 11 }} />
              <ReferenceLine y={1} stroke={C.warn} strokeDasharray="3 3" label={{ value: '1%', fill: C.warn, fontSize: 11 }} />
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
              <div className="v2-list">
                {treasury.upcoming.slice(0, 8).map((a, i) => (
                  <div key={i} className="v2-row">
                    <span className="v2-nowrap" style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{a.auction_date}</span>
                    <span style={{ flex: 1, fontSize: 14, color: 'var(--text-2)' }}>{a.term} {a.type}</span>
                    <span style={{ color: a.offering_amount_b && a.offering_amount_b > 50 ? 'var(--warn)' : 'var(--text-2)', fontSize: 14 }}>
                      {a.offering_amount_b != null ? `$${fmtFixed(a.offering_amount_b, 1)}B` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {treasury.recent.length > 0 && (
            <Card>
              <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 10 }}>최근 경매 결과</div>
              <div className="v2-list">
                {treasury.recent.slice(0, 8).map((a, i) => (
                  <div key={i} className="v2-row">
                    <span className="v2-nowrap" style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{a.auction_date}</span>
                    <span style={{ flex: 1, fontSize: 14, color: 'var(--text-2)' }}>{a.term}</span>
                    <span style={{ color: 'var(--text-2)', fontSize: 14 }}>
                      {a.bid_to_cover != null ? `응찰률 ${fmtFixed(a.bid_to_cover, 2)}x` : '—'}
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
