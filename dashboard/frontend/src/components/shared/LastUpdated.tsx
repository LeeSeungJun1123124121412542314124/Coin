// 마지막 업데이트 시간 표시 컴포넌트
interface Props {
  timestamp: Date | null
}

export default function LastUpdated({ timestamp }: Props) {
  if (!timestamp) return null
  const diff = Math.round((Date.now() - timestamp.getTime()) / 60000)
  const text = diff < 1 ? '방금 전' : `${diff}분 전`
  return (
    <div style={{ color: '#64748b', fontSize: '0.75rem', textAlign: 'right', marginBottom: 8 }}>
      마지막 업데이트: {text}
    </div>
  )
}
