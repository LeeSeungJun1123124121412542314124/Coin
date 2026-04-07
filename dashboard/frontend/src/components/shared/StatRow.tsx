interface StatRowProps {
  label: string
  value: string | number | null | undefined
  change?: number | null
  unit?: string
  highlight?: 'up' | 'down' | 'neutral'
}

export function StatRow({ label, value, change, unit = '', highlight }: StatRowProps) {
  const changeColor =
    change == null ? '#94a3b8'
    : change > 0 ? '#4ade80'
    : change < 0 ? '#f87171'
    : '#94a3b8'

  const valColor =
    highlight === 'up' ? '#4ade80'
    : highlight === 'down' ? '#f87171'
    : '#e2e8f0'

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #1e293b' }}>
      <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{label}</span>
      <span style={{ color: valColor, fontSize: '0.875rem', fontWeight: 500 }}>
        {value ?? '—'}{unit}
        {change != null && (
          <span style={{ color: changeColor, marginLeft: 6, fontSize: '0.75rem' }}>
            {change > 0 ? '+' : ''}{change.toFixed(2)}%
          </span>
        )}
      </span>
    </div>
  )
}
