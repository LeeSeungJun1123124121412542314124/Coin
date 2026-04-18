import { useState } from 'react'
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

interface RowState {
  ticker: string
  loading: boolean
  error: string | null
  saved: boolean
}

export function StockSlotEditor({ market, slots, onUpdate }: StockSlotEditorProps) {
  const [rows, setRows] = useState<RowState[]>(
    slots.map(s => ({
      ticker: s.ticker,
      loading: false,
      error: null,
      saved: false,
    }))
  )

  const setRow = (i: number, patch: Partial<RowState>) =>
    setRows(prev => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  const handleSave = async (i: number, position: number) => {
    const row = rows[i]
    if (!row.ticker.trim()) {
      setRow(i, { error: '티커를 입력해주세요.' })
      return
    }
    setRow(i, { loading: true, error: null, saved: false })
    try {
      await apiFetch(`/api/stock-slots/${market}/${position}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: row.ticker.trim() }),
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
          <div key={slot.position} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {/* 슬롯 번호 라벨 */}
            <div style={{ color: '#94a3b8', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              슬롯 #{slot.position}
            </div>

            {/* 입력 + 버튼 행 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                value={row.ticker}
                disabled={row.loading}
                placeholder="티커 (예: 005930.KS)"
                onChange={e => setRow(i, { ticker: e.target.value.toUpperCase(), saved: false })}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSave(i, slot.position)
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

              {/* 확인 버튼 */}
              <button
                onClick={() => handleSave(i, slot.position)}
                disabled={row.loading}
                title="저장"
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
                ) : row.saved ? '✓' : '저장'}
              </button>
            </div>

            {/* 에러 텍스트 */}
            {row.error && (
              <div style={{ color: '#f87171', fontSize: '0.7rem' }}>{row.error}</div>
            )}
          </div>
        )
      })}

      {/* 스피너 keyframe 인젝션 */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
