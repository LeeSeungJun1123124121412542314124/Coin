import { AreaChart, Area, Tooltip, ResponsiveContainer, XAxis } from 'recharts'
import { useId } from 'react'
import { Card } from './Card'
import { fmt } from '../../lib/format'

interface GlobalMarketCardProps {
  data: {
    total_market_cap_usd: number | null
    market_cap_change_24h: number | null
    btc_dominance: number | null
    eth_dominance: number | null
    market_cap_chart: Array<{ t: number; v: number }> | null
  }
}

export function GlobalMarketCard({ data }: GlobalMarketCardProps) {
  const uid = useId()
  const gradId = `mcapGrad-${uid.replace(/:/g, '')}`

  const {
    total_market_cap_usd,
    market_cap_change_24h,
    btc_dominance,
    eth_dominance,
    market_cap_chart,
  } = data

  // 도미넌스 계산
  const btcDom = btc_dominance ?? 0
  const ethDom = eth_dominance ?? 0
  const othersDom = Math.max(0, 100 - btcDom - ethDom)

  const changePositive =
    market_cap_change_24h != null && market_cap_change_24h >= 0
  const changeColor = changePositive ? '#4ade80' : '#f87171'
  const changeText =
    market_cap_change_24h != null
      ? `${changePositive ? '+' : ''}${market_cap_change_24h.toFixed(2)}%`
      : null

  const chartData = market_cap_chart ?? []
  const hasChart = chartData.length >= 2
  // eth_dominance가 null이어도 BTC + 기타 바는 표시
  const hasDominance = btc_dominance != null

  return (
    <Card>
      {/* 상단 배지 */}
      <div
        style={{
          color: '#94a3b8',
          fontSize: '0.75rem',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          marginBottom: 6,
        }}
      >
        암호화폐 시가총액 TOTAL
      </div>

      {/* 시총 + 24h 변화 */}
      <div style={{ display: 'flex', alignItems: 'baseline' }}>
        <span
          style={{
            fontSize: '1.6rem',
            fontWeight: 700,
            color: '#e2e8f0',
          }}
        >
          {fmt(total_market_cap_usd)}
        </span>
        {changeText != null && (
          <span
            style={{
              color: changeColor,
              fontSize: '0.85rem',
              marginLeft: 8,
            }}
          >
            {changeText}
          </span>
        )}
      </div>

      {/* Area 차트 */}
      {hasChart && (
        <div style={{ marginTop: 10, height: 48 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
            >
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" hide />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 6,
                  fontSize: '0.7rem',
                }}
                formatter={(v) => [fmt(Number(v)), '시총']}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke="#a78bfa"
                strokeWidth={1.5}
                fill={`url(#${gradId})`}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 도미넌스 가로 바 */}
      {hasDominance && (
        <div
          style={{
            marginTop: 10,
            display: 'flex',
            height: 6,
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div style={{ flex: btcDom, background: '#3b82f6' }} />
          {eth_dominance != null && <div style={{ flex: ethDom, background: '#10b981' }} />}
          <div style={{ flex: othersDom, background: '#ef4444' }} />
        </div>
      )}

      {/* 도미넌스 범례 */}
      {hasDominance && (
        <div
          style={{
            marginTop: 6,
            display: 'flex',
            gap: 10,
            flexWrap: 'wrap',
            fontSize: '0.7rem',
            color: '#94a3b8',
          }}
        >
          <span>
            <span style={{ color: '#3b82f6' }}>●</span> BTC{' '}
            {btcDom.toFixed(1)}%
          </span>
          {eth_dominance != null && (
            <span>
              <span style={{ color: '#10b981' }}>●</span> ETH{' '}
              {ethDom.toFixed(1)}%
            </span>
          )}
          <span>
            <span style={{ color: '#ef4444' }}>●</span> 기타{' '}
            {othersDom.toFixed(1)}%
          </span>
        </div>
      )}
    </Card>
  )
}
