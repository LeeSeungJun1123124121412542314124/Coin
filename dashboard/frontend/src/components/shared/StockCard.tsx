import { Card } from './Card'
import { changeColor, changeArrow } from '../../lib/theme'
import { fmtFixed } from '../../lib/format'

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
      style={{ cursor: tv_symbol ? 'pointer' : 'default', transition: 'border-color 0.15s', padding: '16px 12px' }}
    >
      <div className="stock-card-name" style={{ color: 'var(--text-2)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
        {name}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', columnGap: 8, rowGap: 2 }}>
        <span className="stock-card-price" style={{ fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
          {price != null ? price.toLocaleString() : '—'}
        </span>
        {change_pct != null && (
          <span style={{ fontSize: '0.85rem', color, fontWeight: 600, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
            {changeArrow(change_pct)} {fmtFixed(Math.abs(change_pct), 2)}%
          </span>
        )}
      </div>

      {(high != null || low != null) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', columnGap: 10, marginTop: 4, fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
          {high != null && (
            <span style={{ whiteSpace: 'nowrap' }}>
              <span style={{ color: 'var(--up)' }}>H </span>
              <span style={{ color: 'var(--text-2)' }}>{high.toLocaleString()}</span>
            </span>
          )}
          {low != null && (
            <span style={{ whiteSpace: 'nowrap' }}>
              <span style={{ color: 'var(--down)' }}>L </span>
              <span style={{ color: 'var(--text-2)' }}>{low.toLocaleString()}</span>
            </span>
          )}
        </div>
      )}
    </Card>
  )
}
