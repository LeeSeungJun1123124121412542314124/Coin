import { AreaChart, Area, XAxis, YAxis, ReferenceLine, ResponsiveContainer, Tooltip } from 'recharts'

interface HistoryPoint {
  date: string
  value: number
}

interface AltcoinSeasonProps {
  index_value: number
  season_label: 'altcoin_season' | 'neutral' | 'bitcoin_season'
  history: HistoryPoint[]
  cached_at: string
  is_stale: boolean
}

const LABEL_MAP = {
  altcoin_season: { text: '알트코인 시즌', color: '#4ade80' },
  neutral: { text: '중립', color: '#94a3b8' },
  bitcoin_season: { text: '비트코인 시즌', color: '#f87171' },
}

function hoursAgo(isoString: string): number {
  const diffMs = Date.now() - new Date(isoString).getTime()
  return Math.floor(diffMs / (1000 * 60 * 60))
}

export function AltcoinSeasonCard({ index_value, season_label, history, cached_at, is_stale }: AltcoinSeasonProps) {
  const { text: labelText, color: labelColor } = LABEL_MAP[season_label]

  return (
    <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16 }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          알트코인 시즌 지수
        </span>
        {is_stale && (
          <span style={{ color: '#64748b', fontSize: '0.68rem' }}>
            {hoursAgo(cached_at)}시간 전 업데이트
          </span>
        )}
      </div>

      {/* 현재 지수 + 라벨 */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: '2.2rem', fontWeight: 700, color: '#e2e8f0', lineHeight: 1 }}>
          {index_value}
        </span>
        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: labelColor }}>
          {labelText}
        </span>
      </div>

      {/* 90일 추이 차트 */}
      <ResponsiveContainer width="100%" height={100}>
        <AreaChart data={history} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
          <defs>
            <linearGradient id="altcoinGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fill: '#475569', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            interval={Math.floor(history.length / 4)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: '#475569', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            ticks={[0, 25, 50, 75, 100]}
          />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6, fontSize: '0.75rem' }}
            labelStyle={{ color: '#94a3b8' }}
            itemStyle={{ color: '#60a5fa' }}
            formatter={(v) => (v != null ? Number(v) : '')}
          />
          <ReferenceLine y={75} stroke="#4ade80" strokeDasharray="3 3" strokeOpacity={0.6} />
          <ReferenceLine y={25} stroke="#f87171" strokeDasharray="3 3" strokeOpacity={0.6} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#60a5fa"
            strokeWidth={1.5}
            fill="url(#altcoinGrad)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* 임계값 범례 */}
      <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: '0.65rem' }}>
        <span><span style={{ color: '#4ade80' }}>— </span><span style={{ color: '#475569' }}>75+ 알트코인 시즌</span></span>
        <span><span style={{ color: '#f87171' }}>— </span><span style={{ color: '#475569' }}>25- 비트코인 시즌</span></span>
      </div>
    </div>
  )
}
