import { Card } from './Card'

interface StockCardProps {
  ticker: string
  name: string
  tv_symbol: string | null
  price: number | null
  change_pct: number | null
  sparkline: number[]
  high: number | null
  low: number | null
  onOpenModal: (tv_symbol: string, name: string) => void
}

export function StockCard({ name, tv_symbol, price, change_pct, high, low, onOpenModal }: StockCardProps) {
  const isPositive = (change_pct ?? 0) >= 0
  const color = isPositive ? '#4ade80' : '#f87171'

  const handleClick = () => {
    if (tv_symbol) onOpenModal(tv_symbol, name)
  }

  return (
    <Card
      onClick={tv_symbol ? handleClick : undefined}
      className={tv_symbol ? 'stock-card' : ''}
      style={{ cursor: tv_symbol ? 'pointer' : 'default', transition: 'border-color 0.15s' }}
    >
      <div style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
        {name}
      </div>

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

      {(high != null || low != null) && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: '0.72rem' }}>
          {high != null && (
            <span>
              <span style={{ color: '#f87171' }}>H </span>
              <span style={{ color: '#94a3b8' }}>{high.toLocaleString()}</span>
            </span>
          )}
          {low != null && (
            <span>
              <span style={{ color: '#4ade80' }}>L </span>
              <span style={{ color: '#94a3b8' }}>{low.toLocaleString()}</span>
            </span>
          )}
        </div>
      )}
    </Card>
  )
}
