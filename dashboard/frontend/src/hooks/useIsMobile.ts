import { useEffect, useState } from 'react'

// 화면 폭이 모바일(<768px)인지 — 표와 카드 목록 중 하나만 그리기 위해 쓴다
const MOBILE_QUERY = '(max-width: 767px)'

export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY)
    const onChange = () => setMobile(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return mobile
}
