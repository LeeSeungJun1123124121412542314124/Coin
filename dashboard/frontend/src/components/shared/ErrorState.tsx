// 에러 상태 공통 컴포넌트 — 재시도 버튼 포함
interface Props {
  error: string
  onRetry?: () => void
}

export default function ErrorState({ error, onRetry }: Props) {
  return (
    <div style={{ color: '#f87171', padding: 32, textAlign: 'center' }}>
      <p style={{ marginBottom: 12 }}>데이터 로드 실패: {error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '8px 20px',
            background: '#334155',
            color: '#e2e8f0',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          다시 시도
        </button>
      )}
    </div>
  )
}
