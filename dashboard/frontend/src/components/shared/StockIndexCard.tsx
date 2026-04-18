import { AreaChart, Area, ResponsiveContainer, XAxis, Tooltip } from 'recharts'
import { useId } from 'react'
import { Card } from './Card'

interface StockIndexCardProps {
  name: string
  ticker: string
  price: number | null
  change_pct: number | null
  sparkline: number[]
  onOpenModal: (ticker: string) => void
}

export function StockIndexCard({ name, ticker, price, change_pct, sparkline, onOpenModal }: StockIndexCardProps) {
  const uid = useId()
  const gradId = `stockGrad-${uid.replace(/:/g, '')}`

  const isPositive = (change_pct ?? 0) >= 0
  const color = isPositive ? '#4ade80' : '#f87171'

  const chartData = sparkline.map((v, i) => ({ i, v }))

  return (
    <Card onClick={() => onOpenModal(ticker)} style={{ cursor: 'pointer' }}>
      {/* 배지 */}
      <div style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
        {name}
      </div>

      {/* 현재가 + 변동률 */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: '1.4rem', fontWeight: 700, color: '#e2e8f0' }}>
          {price != null ? price.toLocaleString() : '—'}
        </span>
        {change_pct != null && (
          <span style={{ fontSize: '0.85rem', color, fontWeight: 600 }}>
            {isPositive ? '+' : ''}{change_pct.toFixed(2)}%
          </span>
        )}
      </div>

      {/* 스파크라인 */}
      {chartData.length >= 2 && (
        <div style={{ marginTop: 10, height: 48 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="i" hide />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: '0.7rem' }}
                formatter={(v) => [Number(v).toLocaleString(), name]}
              />
              <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} fill={`url(#${gradId})`} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
