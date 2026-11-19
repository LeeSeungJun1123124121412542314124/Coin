import { Card } from './Card'
import { changeColor, changeArrow } from '../../lib/theme'

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
  const color = changeColor(change_pct)

  const handleClick = () => {
    if (tv_symbol) onOpenModal(tv_symbol, name)
  }

  return (
    <Card
      onClick={tv_symbol ? handleClick : undefined}
      className={tv_symbol ? 'stock-card' : ''}
      style={{ cursor: tv_symbol ? 'pointer' : 'default', transition: 'border-color 0.15s' }}
    >
      <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
        {name}
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
          {price != null ? price.toLocaleString() : '—'}
        </span>
        {change_pct != null && (
          <span style={{ fontSize: '0.85rem', color, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
            {changeArrow(change_pct)} {change_pct > 0 ? '+' : ''}{change_pct.toFixed(2)}%
          </span>
        )}
      </div>

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
    </Card>
  )
}
