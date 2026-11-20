import { useState, useEffect, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, ReferenceLine,
  ResponsiveContainer, Tooltip, Legend,
} from 'recharts'
import { C, softBg } from '../../lib/theme'

// 모바일 뷰포트 감지 — 인라인 스타일 카드라 미디어쿼리 대신 JS로 분기
function useIsMobile(breakpoint = 768): boolean {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' && window.innerWidth <= breakpoint
  )
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`)
    const handler = () => setIsMobile(mq.matches)
    handler()
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [breakpoint])
  return isMobile
}

interface HistoryPoint {
  date: string
  value: number
  market_cap: number
}

interface SeasonExtreme {
  value: number
  date: string
  season_label: string
}

interface AltcoinSeasonProps {
  index_value: number
  season_label: 'altcoin_season' | 'neutral' | 'bitcoin_season'
  history: HistoryPoint[]
  cached_at: string
  is_stale: boolean
  yesterday_value: number | null
  last_week_value: number | null
  last_month_value: number | null
  yearly_high: SeasonExtreme | null
  yearly_low: SeasonExtreme | null
}

const SEASON_CONFIG = {
  altcoin_season: { text: '알트코인 시즌', color: C.info, bg: softBg(C.info, 0.14) },
  neutral:        { text: '중립',           color: C.text2, bg: C.surface2 },
  bitcoin_season: { text: '비트코인 시즌', color: C.warn, bg: softBg(C.warn, 0.14) },
}

function formatMcap(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9)  return `${(v / 1e9).toFixed(1)}B`
  return `${(v / 1e6).toFixed(0)}M`
}

function SeasonBadge({ label, value }: { label: string; value: number }) {
  const cfg = SEASON_CONFIG[label as keyof typeof SEASON_CONFIG] ?? SEASON_CONFIG.neutral
  return (
    <span style={{
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}55`,
      borderRadius: 6, padding: '2px 10px', fontSize: '0.78rem', fontWeight: 600,
    }}>
      {cfg.text} - {value}
    </span>
  )
}

function HistoryRow({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
      <span style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>{label}</span>
      <span style={{ background: softBg(C.warn, 0.14), color: C.warnText, borderRadius: 20, padding: '2px 12px', fontSize: '0.82rem', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
        {value}
      </span>
    </div>
  )
}

type Period = '7d' | '30d' | '90d'

export function AltcoinSeasonCard(props: AltcoinSeasonProps) {
  const {
    index_value, season_label, history,
    yesterday_value, last_week_value, last_month_value,
    yearly_high, yearly_low,
  } = props

  const [period, setPeriod] = useState<Period>('90d')
  const isMobile = useIsMobile()
  const cfg = SEASON_CONFIG[season_label]

  const sliderPct = index_value
  const sliderColor = index_value >= 75 ? C.info : index_value >= 25 ? C.text2 : C.warn

  const chartData = useMemo(() => {
    const n = period === '7d' ? 7 : period === '30d' ? 30 : 90
    return history.slice(-n)
  }, [history, period])

  const mcapDomain = useMemo(() => {
    const vals = chartData.map(d => d.market_cap).filter(Boolean)
    if (!vals.length) return ['auto', 'auto'] as const
    const min = Math.min(...vals) * 0.95
    const max = Math.max(...vals) * 1.05
    return [min, max] as const
  }, [chartData])

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-card)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 0 }}>

        {/* ── 좌측 패널 (모바일에선 상단 전체폭) ── */}
        <div style={{
          width: isMobile ? '100%' : 280,
          minWidth: isMobile ? 0 : 280,
          padding: '20px 20px',
          borderRight: isMobile ? 'none' : '1px solid var(--border)',
          borderBottom: isMobile ? '1px solid var(--border)' : 'none',
          display: 'flex', flexDirection: 'column', gap: 20,
          boxSizing: 'border-box',
        }}>

          {/* 헤더 + 현재값 */}
          <div>
            <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 8 }}>
              CMC 알트코인 시즌 지수
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: '2.6rem', fontWeight: 700, color: 'var(--text)', lineHeight: 1, fontFamily: 'var(--font-mono)' }}>{index_value}</span>
              <span style={{ color: 'var(--text-3)', fontSize: '1rem' }}>/100</span>
            </div>
            <div style={{ color: cfg.color, fontSize: '0.82rem', fontWeight: 600, marginTop: 4 }}>{cfg.text}</div>
          </div>

          {/* 슬라이더 게이지 */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-3)', marginBottom: 4 }}>
              <span>비트코인 시즌</span>
              <span>알트코인 시즌</span>
            </div>
            <div style={{ position: 'relative', height: 8, borderRadius: 4, background: 'linear-gradient(to right, var(--warn), var(--text-2) 50%, var(--info))', marginBottom: 2 }}>
              <div style={{
                position: 'absolute', top: '50%', transform: 'translate(-50%, -50%)',
                left: `${sliderPct}%`,
                width: 14, height: 14, borderRadius: '50%',
                background: 'var(--text)', border: `2px solid ${sliderColor}`,
                boxShadow: `0 0 6px ${sliderColor}88`,
              }} />
            </div>
          </div>

          {/* Historical Values */}
          <div>
            <div style={{ color: 'var(--text)', fontSize: '0.82rem', fontWeight: 600, marginBottom: 8 }}>과거 수치</div>
            <HistoryRow label="어제"    value={yesterday_value} />
            <HistoryRow label="지난 주" value={last_week_value} />
            <HistoryRow label="지난 달" value={last_month_value} />
          </div>

          {/* Yearly High & Low */}
          {(yearly_high || yearly_low) && (
            <div>
              <div style={{ color: 'var(--text)', fontSize: '0.82rem', fontWeight: 600, marginBottom: 10 }}>연간 고저</div>
              {yearly_high && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ color: 'var(--text-3)', fontSize: '0.78rem' }}>연간 최고 ({yearly_high.date})</span>
                  <SeasonBadge label={yearly_high.season_label} value={yearly_high.value} />
                </div>
              )}
              {yearly_low && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: '0.78rem' }}>연간 최저 ({yearly_low.date})</span>
                  <SeasonBadge label={yearly_low.season_label} value={yearly_low.value} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── 우측 차트 패널 ── */}
        <div style={{ flex: 1, padding: '20px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* 차트 헤더 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <span style={{ color: 'var(--text)', fontSize: '0.88rem', fontWeight: 600 }}>알트코인 시즌 지수 차트</span>
              <div style={{ display: 'flex', gap: 12, fontSize: '0.75rem', color: 'var(--text-2)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ display: 'inline-block', width: 20, borderTop: `2px dashed ${C.info}`, verticalAlign: 'middle' }} />
                  알트코인 시즌 (75)
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ display: 'inline-block', width: 20, borderTop: `2px dashed ${C.warn}`, verticalAlign: 'middle' }} />
                  비트코인 시즌 (25)
                </span>
              </div>
            </div>
            <div className="tap-seg" style={{ display: 'flex', gap: 4 }}>
              {(['7d', '30d', '90d'] as Period[]).map(p => (
                <button key={p} onClick={() => setPeriod(p)} style={{
                  background: period === p ? 'var(--seg-active)' : 'transparent',
                  color: period === p ? 'var(--text)' : 'var(--text-3)',
                  border: '1px solid ' + (period === p ? 'var(--border-strong)' : 'var(--border)'),
                  borderRadius: 6, padding: '3px 10px', fontSize: '0.75rem', cursor: 'pointer',
                }}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* 듀얼 축 차트 */}
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="mcapGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.text2} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={C.text2} stopOpacity={0.02} />
                </linearGradient>
              </defs>

              <XAxis
                dataKey="date"
                tick={{ fill: C.text3, fontSize: 11 }}
                tickLine={false} axisLine={false}
                interval={Math.max(1, Math.floor(chartData.length / 6))}
              />

              {/* 좌측 Y축: 시총 */}
              <YAxis
                yAxisId="mcap"
                orientation="left"
                domain={mcapDomain}
                tickFormatter={formatMcap}
                tick={{ fill: C.text3, fontSize: 11 }}
                tickLine={false} axisLine={false}
                width={52}
              />

              {/* 우측 Y축: 지수 */}
              <YAxis
                yAxisId="asi"
                orientation="right"
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                tick={{ fill: C.text3, fontSize: 11 }}
                tickLine={false} axisLine={false}
                width={32}
              />

              <Tooltip
                contentStyle={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: '0.75rem' }}
                labelStyle={{ color: C.text2 }}
                formatter={(v, name) => {
                  const num = typeof v === 'number' ? v : Number(Array.isArray(v) ? v[0] : (v ?? 0));
                  return name === 'AMC' ? [formatMcap(num), '알트코인 시총'] : [num, '알트코인 시즌 지수'];
                }}
              />


              <ReferenceLine yAxisId="asi" y={75} stroke={C.info} strokeDasharray="3 3" strokeOpacity={0.5} />
              <ReferenceLine yAxisId="asi" y={25} stroke={C.warn} strokeDasharray="3 3" strokeOpacity={0.5} />

              <Legend
                wrapperStyle={{ fontSize: '0.75rem', color: C.text2, paddingTop: 8 }}
                formatter={(v) => v === 'value' ? '알트코인 시즌 지수' : '알트코인 시총'}
              />

              {/* 시총 영역 */}
              <Area
                yAxisId="mcap"
                dataKey="market_cap"
                name="AMC"
                stroke={C.text2}
                strokeWidth={1.5}
                fill="url(#mcapGrad)"
                dot={false}
                isAnimationActive={false}
              />

              {/* 지수 라인 */}
              <Line
                yAxisId="asi"
                dataKey="value"
                name="value"
                stroke={C.warn}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>

          <div style={{ textAlign: 'right', color: 'var(--text-3)', fontSize: '0.75rem' }}>© CoinMarketCap</div>
        </div>
      </div>
    </div>
  )
}
