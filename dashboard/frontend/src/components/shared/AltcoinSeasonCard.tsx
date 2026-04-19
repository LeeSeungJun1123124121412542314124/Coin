import { useState, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, ReferenceLine,
  ResponsiveContainer, Tooltip, Legend,
} from 'recharts'

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
  altcoin_season: { text: '알트코인 시즌', color: '#60a5fa', bg: '#1e3a5f' },
  neutral:        { text: '중립',           color: '#94a3b8', bg: '#1e293b' },
  bitcoin_season: { text: '비트코인 시즌', color: '#f97316', bg: '#3b1f0d' },
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
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #1e293b' }}>
      <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>{label}</span>
      <span style={{ background: '#92400e', color: '#fcd34d', borderRadius: 20, padding: '2px 12px', fontSize: '0.82rem', fontWeight: 600 }}>
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
  const cfg = SEASON_CONFIG[season_label]

  const sliderPct = index_value
  const sliderColor = index_value >= 75 ? '#60a5fa' : index_value >= 25 ? '#94a3b8' : '#f97316'

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
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ display: 'flex', gap: 0 }}>

        {/* ── 좌측 패널 ── */}
        <div style={{ width: 280, minWidth: 280, padding: '20px 20px', borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* 헤더 + 현재값 */}
          <div>
            <div style={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 8 }}>
              CMC 알트코인 시즌 지수
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: '2.6rem', fontWeight: 700, color: '#e2e8f0', lineHeight: 1 }}>{index_value}</span>
              <span style={{ color: '#475569', fontSize: '1rem' }}>/100</span>
            </div>
            <div style={{ color: cfg.color, fontSize: '0.82rem', fontWeight: 600, marginTop: 4 }}>{cfg.text}</div>
          </div>

          {/* 슬라이더 게이지 */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: '#64748b', marginBottom: 4 }}>
              <span>비트코인 시즌</span>
              <span>알트코인 시즌</span>
            </div>
            <div style={{ position: 'relative', height: 8, borderRadius: 4, background: 'linear-gradient(to right, #f97316, #94a3b8 50%, #60a5fa)', marginBottom: 2 }}>
              <div style={{
                position: 'absolute', top: '50%', transform: 'translate(-50%, -50%)',
                left: `${sliderPct}%`,
                width: 14, height: 14, borderRadius: '50%',
                background: '#e2e8f0', border: `2px solid ${sliderColor}`,
                boxShadow: `0 0 6px ${sliderColor}88`,
              }} />
            </div>
          </div>

          {/* Historical Values */}
          <div>
            <div style={{ color: '#e2e8f0', fontSize: '0.82rem', fontWeight: 600, marginBottom: 8 }}>과거 수치</div>
            <HistoryRow label="어제"    value={yesterday_value} />
            <HistoryRow label="지난 주" value={last_week_value} />
            <HistoryRow label="지난 달" value={last_month_value} />
          </div>

          {/* Yearly High & Low */}
          {(yearly_high || yearly_low) && (
            <div>
              <div style={{ color: '#e2e8f0', fontSize: '0.82rem', fontWeight: 600, marginBottom: 10 }}>연간 고저</div>
              {yearly_high && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ color: '#64748b', fontSize: '0.78rem' }}>연간 최고 ({yearly_high.date})</span>
                  <SeasonBadge label={yearly_high.season_label} value={yearly_high.value} />
                </div>
              )}
              {yearly_low && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#64748b', fontSize: '0.78rem' }}>연간 최저 ({yearly_low.date})</span>
                  <SeasonBadge label={yearly_low.season_label} value={yearly_low.value} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── 우측 차트 패널 ── */}
        <div style={{ flex: 1, padding: '20px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* 차트 헤더 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ color: '#e2e8f0', fontSize: '0.88rem', fontWeight: 600 }}>알트코인 시즌 지수 차트</span>
              <div style={{ display: 'flex', gap: 12, fontSize: '0.72rem', color: '#94a3b8' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ display: 'inline-block', width: 20, borderTop: '2px dashed #60a5fa', verticalAlign: 'middle' }} />
                  알트코인 시즌 (75)
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ display: 'inline-block', width: 20, borderTop: '2px dashed #f97316', verticalAlign: 'middle' }} />
                  비트코인 시즌 (25)
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['7d', '30d', '90d'] as Period[]).map(p => (
                <button key={p} onClick={() => setPeriod(p)} style={{
                  background: period === p ? '#334155' : 'transparent',
                  color: period === p ? '#e2e8f0' : '#475569',
                  border: '1px solid ' + (period === p ? '#475569' : '#1e293b'),
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
                  <stop offset="5%"  stopColor="#94a3b8" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#94a3b8" stopOpacity={0.02} />
                </linearGradient>
              </defs>

              <XAxis
                dataKey="date"
                tick={{ fill: '#475569', fontSize: 9 }}
                tickLine={false} axisLine={false}
                interval={Math.max(1, Math.floor(chartData.length / 6))}
              />

              {/* 좌측 Y축: 시총 */}
              <YAxis
                yAxisId="mcap"
                orientation="left"
                domain={mcapDomain}
                tickFormatter={formatMcap}
                tick={{ fill: '#475569', fontSize: 9 }}
                tickLine={false} axisLine={false}
                width={52}
              />

              {/* 우측 Y축: 지수 */}
              <YAxis
                yAxisId="asi"
                orientation="right"
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                tick={{ fill: '#475569', fontSize: 9 }}
                tickLine={false} axisLine={false}
                width={32}
              />

              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: '0.75rem' }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v: number, name: string) =>
                  name === 'AMC' ? [formatMcap(v), '알트코인 시총'] : [v, '알트코인 시즌 지수']
                }
              />


              <ReferenceLine yAxisId="asi" y={75} stroke="#60a5fa" strokeDasharray="3 3" strokeOpacity={0.5} />
              <ReferenceLine yAxisId="asi" y={25} stroke="#f97316" strokeDasharray="3 3" strokeOpacity={0.5} />

              <Legend
                wrapperStyle={{ fontSize: '0.72rem', color: '#94a3b8', paddingTop: 8 }}
                formatter={(v) => v === 'value' ? '알트코인 시즌 지수' : '알트코인 시총'}
              />

              {/* 시총 영역 */}
              <Area
                yAxisId="mcap"
                dataKey="market_cap"
                name="AMC"
                stroke="#94a3b8"
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
                stroke="#f97316"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>

          <div style={{ textAlign: 'right', color: '#334155', fontSize: '0.65rem' }}>© CoinMarketCap</div>
        </div>
      </div>
    </div>
  )
}
