import { useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'

interface Slot {
  position: number
  ticker: string
}

interface StockSlotEditorProps {
  market: 'kr' | 'us'
  slots: Slot[]
  onUpdate: () => void
}

interface Suggestion {
  ticker: string
  name: string
}

interface RowState {
  ticker: string
  loading: boolean
  error: string | null
  saved: boolean
  suggestions: Suggestion[]
  showDropdown: boolean
}

export function StockSlotEditor({ market, slots, onUpdate }: StockSlotEditorProps) {
  const [rows, setRows] = useState<RowState[]>(
    slots.map(s => ({
      ticker: s.ticker,
      loading: false,
      error: null,
      saved: false,
      suggestions: [],
      showDropdown: false,
    }))
  )
  const blurTimers = useRef<(ReturnType<typeof setTimeout> | null)[]>(slots.map(() => null))

  const setRow = (i: number, patch: Partial<RowState>) =>
    setRows(prev => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  const handleSearch = async (i: number) => {
    const row = rows[i]
    const query = row.ticker.trim()
    if (!query) {
      setRow(i, { error: '검색어를 입력해주세요.' })
      return
    }
    setRow(i, { loading: true, error: null, saved: false, showDropdown: false })
    try {
      const results: Suggestion[] = await apiFetch(`/api/stock-search?q=${encodeURIComponent(query)}&market=${market}`)
      setRow(i, { loading: false, suggestions: results, showDropdown: true })
    } catch {
      setRow(i, { loading: false, error: '검색 실패', showDropdown: false })
    }
  }

  const handleSelect = async (i: number, position: number, suggestion: Suggestion) => {
    setRow(i, { ticker: suggestion.ticker, loading: true, error: null, saved: false, showDropdown: false, suggestions: [] })
    try {
      await apiFetch(`/api/stock-slots/${market}/${position}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: suggestion.ticker }),
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
          <div key={slot.position} style={{ display: 'flex', flexDirection: 'column', gap: 4, position: 'relative' }}>
            <div style={{ color: '#94a3b8', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              슬롯 #{slot.position}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                value={row.ticker}
                disabled={row.loading}
                placeholder="티커 또는 종목명 검색"
                onChange={e => setRow(i, { ticker: e.target.value, saved: false, showDropdown: false, suggestions: [] })}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSearch(i)
                  if (e.key === 'Escape') setRow(i, { showDropdown: false })
                }}
                onBlur={() => {
                  blurTimers.current[i] = setTimeout(() => setRow(i, { showDropdown: false }), 150)
                }}
                style={{
                  flex: 1,
                  minWidth: 0,
                  background: '#0f172a',
                  border: `1px solid ${row.error ? '#f87171' : '#334155'}`,
                  borderRadius: 4,
                  color: '#e2e8f0',
                  fontSize: '0.85rem',
                  padding: '3px 6px',
                  outline: 'none',
                }}
              />

              <button
                onClick={() => handleSearch(i)}
                disabled={row.loading}
                title="검색"
                style={{
                  background: 'transparent',
                  border: '1px solid #60a5fa',
                  borderRadius: 4,
                  color: '#60a5fa',
                  cursor: row.loading ? 'not-allowed' : 'pointer',
                  fontSize: '0.85rem',
                  padding: '2px 6px',
                  lineHeight: 1.4,
                }}
              >
                {row.loading ? (
                  <span
                    style={{
                      display: 'inline-block',
                      width: 10,
                      height: 10,
                      border: '2px solid #60a5fa',
                      borderTopColor: 'transparent',
                      borderRadius: '50%',
                      animation: 'spin 0.6s linear infinite',
                      verticalAlign: 'middle',
                    }}
                  />
                ) : row.saved ? '✓' : '검색'}
              </button>
            </div>

            {/* 검색 결과 드롭다운 */}
            {row.showDropdown && (
              <div
                style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  zIndex: 50,
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 6,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                  overflow: 'hidden',
                }}
              >
                {row.suggestions.length === 0 ? (
                  <div style={{ padding: '6px 10px', color: '#94a3b8', fontSize: '0.8rem' }}>
                    검색 결과 없음
                  </div>
                ) : (
                  row.suggestions.map(s => (
                    <div
                      key={s.ticker}
                      onMouseDown={() => {
                        if (blurTimers.current[i]) clearTimeout(blurTimers.current[i]!)
                        handleSelect(i, slot.position, s)
                      }}
                      style={{
                        padding: '6px 10px',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 8,
                        borderBottom: '1px solid #1e293b',
                        background: '#0f172a',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = '#1e3a5f')}
                      onMouseLeave={e => (e.currentTarget.style.background = '#0f172a')}
                    >
                      <span style={{ color: '#60a5fa', fontSize: '0.8rem', fontWeight: 600 }}>{s.ticker}</span>
                      <span style={{ color: '#94a3b8', fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                    </div>
                  ))
                )}
              </div>
            )}

            {row.error && (
              <div style={{ color: '#f87171', fontSize: '0.7rem' }}>{row.error}</div>
            )}
          </div>
        )
      })}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
