import { changeColor, changeArrow } from '../../lib/theme'

interface StatRowProps {
  label: string
  value: string | number | null | undefined
  change?: number | null
  unit?: string
  highlight?: 'up' | 'down' | 'neutral'
}

export function StatRow({ label, value, change, unit = '', highlight }: StatRowProps) {
  const valColor =
    highlight === 'up' ? 'var(--up)'
    : highlight === 'down' ? 'var(--down)'
    : 'var(--text)'

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 44, borderTop: '1px solid var(--line)' }}>
      <span style={{ color: 'var(--text-2)', fontSize: 14 }}>{label}</span>
      <span style={{ color: valColor, fontSize: 15, fontWeight: 500, fontFamily: 'var(--font-mono)' }}>
        {value ?? '—'}{unit}
        {change != null && (
          <span style={{ color: changeColor(change), marginLeft: 6, fontSize: 13 }}>
            {changeArrow(change)} {change > 0 ? '+' : ''}{change.toFixed(2)}%
          </span>
        )}
      </span>
    </div>
  )
}
