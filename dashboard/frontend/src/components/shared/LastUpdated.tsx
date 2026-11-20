import { useEffect } from 'react'

// 마지막으로 성공한 갱신 시각(HH:mm)과 갱신 실패 여부를 앱 헤더로 전달하는 컴포넌트
interface Props {
  timestamp: Date | null
  failed?: boolean
}

export interface LastUpdatedDetail {
  time: string
  failed: boolean
}

export default function LastUpdated({ timestamp, failed = false }: Props) {
  useEffect(() => {
    // 시각이 없으면 빈 값을 보내 이전 화면·탭의 시각이 남지 않게 한다
    const time = timestamp
      ? timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      : ''
    const detail: LastUpdatedDetail = { time, failed }
    window.dispatchEvent(new CustomEvent('dashboard:last-updated', { detail }))
    // 사라질 때(같은 화면의 탭 전환 포함)도 비워, 새 탭이 로딩 중일 때 이전 탭의 시각·경고가 남지 않게 한다
    return () => {
      const cleared: LastUpdatedDetail = { time: '', failed: false }
      window.dispatchEvent(new CustomEvent('dashboard:last-updated', { detail: cleared }))
    }
  }, [timestamp, failed])

  return null
}
