import { useEffect } from 'react'

// 마지막 업데이트 시간을 앱 헤더로 전달하는 컴포넌트
interface Props {
  timestamp: Date | null
}

export default function LastUpdated({ timestamp }: Props) {
  useEffect(() => {
    if (!timestamp) return
    const diff = Math.round((Date.now() - timestamp.getTime()) / 60000)
    const text = diff < 1 ? '방금 전' : `${diff}분 전`
    window.dispatchEvent(new CustomEvent('dashboard:last-updated', { detail: text }))
  }, [timestamp])

  return null
}
