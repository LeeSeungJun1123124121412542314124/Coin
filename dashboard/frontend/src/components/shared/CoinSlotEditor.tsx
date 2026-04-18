import { useState } from 'react'

interface CoinSlotEditorProps {
  position: number
  currentSymbol: string
  onSave: (query: string) => void
  onCancel: () => void
  loading: boolean
  error: string | null
}

/** 코인 슬롯 인라인 편집 컴포넌트 */
export function CoinSlotEditor({
  position,
  currentSymbol,
  onSave,
  onCancel,
  loading,
  error,
}: CoinSlotEditorProps) {
  const [inputValue, setInputValue] = useState(currentSymbol)

  const handleSave = () => {
    const trimmed = inputValue.trim()
    if (!trimmed) return
    onSave(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') onCancel()
  }

  return (
    <div
      onClick={e => e.stopPropagation()}
      style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
    >
      {/* 슬롯 번호 라벨 */}
      <div style={{ color: '#94a3b8', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        슬롯 #{position}
      </div>

      {/* 입력 + 버튼 행 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <input
          autoFocus
          value={inputValue}
          disabled={loading}
          placeholder="BTC, DOGE..."
          onChange={e => setInputValue(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          style={{
            flex: 1,
            minWidth: 0,
            background: '#0f172a',
            border: `1px solid ${error ? '#f87171' : '#334155'}`,
            borderRadius: 4,
            color: '#e2e8f0',
            fontSize: '0.85rem',
            padding: '3px 6px',
            outline: 'none',
          }}
        />

        {/* 확인 버튼 */}
        <button
          onClick={handleSave}
          disabled={loading}
          title="저장"
          style={{
            background: 'transparent',
            border: '1px solid #60a5fa',
            borderRadius: 4,
            color: '#60a5fa',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '0.85rem',
            padding: '2px 6px',
            lineHeight: 1.4,
          }}
        >
          {loading ? (
            /* 작은 인라인 스피너 */
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
          ) : '✓'}
        </button>

        {/* 취소 버튼 */}
        <button
          onClick={onCancel}
          disabled={loading}
          title="취소"
          style={{
            background: 'transparent',
            border: '1px solid #475569',
            borderRadius: 4,
            color: '#94a3b8',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '0.85rem',
            padding: '2px 6px',
            lineHeight: 1.4,
          }}
        >
          ✕
        </button>
      </div>

      {/* 에러 텍스트 */}
      {error && (
        <div style={{ color: '#f87171', fontSize: '0.7rem' }}>{error}</div>
      )}

      {/* 스피너 keyframe 인젝션 (전역 style 태그) */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
