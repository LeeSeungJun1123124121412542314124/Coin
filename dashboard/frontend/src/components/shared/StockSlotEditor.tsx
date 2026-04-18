import { useState } from 'react'
import { apiFetch } from '../../lib/api'

interface Slot {
  position: number
  ticker: string
  name: string
  tv_symbol: string | null
}

interface StockSlotEditorProps {
  market: 'kr' | 'us'
  slots: Slot[]
  onUpdate: () => void
}

interface RowState {
  ticker: string
  name: string
  tv_symbol: string
  loading: boolean
  error: string | null
  saved: boolean
}

export function StockSlotEditor({ market, slots, onUpdate }: StockSlotEditorProps) {
  const [rows, setRows] = useState<RowState[]>(
    slots.map(s => ({
      ticker: s.ticker,
      name: s.name,
      tv_symbol: s.tv_symbol ?? '',
      loading: false,
      error: null,
      saved: false,
    }))
  )

  const setRow = (i: number, patch: Partial<RowState>) =>
    setRows(prev => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  const handleSave = async (i: number, position: number) => {
    const row = rows[i]
    if (!row.ticker.trim() || !row.name.trim()) {
      setRow(i, { error: '티커와 이름은 필수입니다.' })
      return
    }
    setRow(i, { loading: true, error: null, saved: false })
    try {
      await apiFetch(`/api/stock-slots/${market}/${position}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: row.ticker.trim(),
          name: row.name.trim(),
          tv_symbol: row.tv_symbol.trim() || null,
        }),
      })
      setRow(i, { loading: false, saved: true })
      onUpdate()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '저장 실패'
      setRow(i, { loading: false, error: msg })
    }
  }

  return (
    <div style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {slots.map((slot, i) => {
        const row = rows[i]
        return (
          <div key={slot.position} style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ color: '#64748b', fontSize: '0.7rem', minWidth: 24 }}>#{slot.position}</span>
            <input
              value={row.ticker}
              disabled={row.loading}
              placeholder="티커 (예: 005930.KS)"
              onChange={e => setRow(i, { ticker: e.target.value, saved: false })}
              style={inputStyle(!!row.error)}
            />
            <input
              value={row.name}
              disabled={row.loading}
              placeholder="이름 (예: 삼성전자)"
              onChange={e => setRow(i, { name: e.target.value, saved: false })}
              style={inputStyle(!!row.error)}
            />
            <input
              value={row.tv_symbol}
              disabled={row.loading}
              placeholder="TV 심볼 (예: KRX:005930)"
              onChange={e => setRow(i, { tv_symbol: e.target.value, saved: false })}
              style={{ ...inputStyle(false), minWidth: 130 }}
            />
            <button
              onClick={() => handleSave(i, slot.position)}
              disabled={row.loading}
              style={btnStyle('#60a5fa')}
            >
              {row.loading ? <Spinner /> : row.saved ? '✓' : '저장'}
            </button>
            {row.error && <span style={{ color: '#f87171', fontSize: '0.7rem' }}>{row.error}</span>}
          </div>
        )
      })}
    </div>
  )
}

function Spinner() {
  return (
    <>
      <span style={{ display: 'inline-block', width: 10, height: 10, border: '2px solid #60a5fa', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite', verticalAlign: 'middle' }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  )
}

function inputStyle(hasError: boolean): React.CSSProperties {
  return {
    flex: 1,
    minWidth: 80,
    background: '#0f172a',
    border: `1px solid ${hasError ? '#f87171' : '#334155'}`,
    borderRadius: 4,
    color: '#e2e8f0',
    fontSize: '0.8rem',
    padding: '3px 6px',
    outline: 'none',
  }
}

function btnStyle(borderColor: string): React.CSSProperties {
  return {
    background: 'transparent',
    border: `1px solid ${borderColor}`,
    borderRadius: 4,
    color: borderColor,
    cursor: 'pointer',
    fontSize: '0.8rem',
    padding: '3px 8px',
    whiteSpace: 'nowrap',
  }
}
