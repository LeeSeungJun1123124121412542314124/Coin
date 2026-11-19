import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, ReferenceLine } from 'recharts'
import { useId } from 'react'
import { Card } from './Card'
import { changeColor, changeArrow } from '../../lib/theme'

interface StockIndexCardProps {
  name: string
  ticker: string
  price: number | null
  change_pct: number | null
  sparkline: number[]
  high: number | null
  low: number | null
  onOpenModal: (ticker: string) => void
}

export function StockIndexCard({ name, ticker, price, change_pct, sparkline, high, low, onOpenModal }: StockIndexCardProps) {
  const uid = useId()
  const gradId = `stockGrad-${uid.replace(/:/g, '')}`

  const color = changeColor(change_pct)

  const chartData = sparkline.map((v, i) => ({ i, v }))

  return (
    <Card className="dashboard-market-card" onClick={() => onOpenModal(ticker)} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column' }}>
      {/* 배지 */}
      <div className="dashboard-card-title" style={{ marginBottom: 6 }}>
        {name}
      </div>

      {/* 현재가 + 변동률 */}
      <div className="dashboard-index-value-row">
        <span className="dashboard-main-value">
          {price != null ? price.toLocaleString() : '—'}
        </span>
        {change_pct != null && (
          <span className="dashboard-index-change" style={{ color }}>
            {changeArrow(change_pct)} {change_pct > 0 ? '+' : ''}{change_pct.toFixed(2)}%
          </span>
        )}
      </div>

      {/* 고가/저가 */}
      {(high != null || low != null) && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: '0.72rem', fontFamily: 'var(--font-mono)' }}>
          {high != null && (
            <span>
              <span style={{ color: 'var(--up)' }}>H </span>
              <span style={{ color: 'var(--text-2)' }}>{high.toLocaleString()}</span>
            </span>
          )}
          {low != null && (
            <span>
              <span style={{ color: 'var(--down)' }}>L </span>
              <span style={{ color: 'var(--text-2)' }}>{low.toLocaleString()}</span>
            </span>
          )}
        </div>
      )}

      {/* 스파크라인 + 기준선 — 항상 카드 하단 고정 */}
      {chartData.length >= 2 && price != null && (
        <div className="dashboard-sparkline" style={{ marginTop: 'auto', paddingTop: 8 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.5} />
                  <stop offset="95%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis dataKey="i" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <ReferenceLine y={price} stroke={color} strokeDasharray="4 3" strokeOpacity={0.4} strokeWidth={1} />
              <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${gradId})`} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
