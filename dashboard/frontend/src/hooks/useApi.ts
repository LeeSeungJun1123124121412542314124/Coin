import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../lib/api'

interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
  isRefreshing: boolean
  refetch: () => void
}

/** 지정 ms 동안 대기 */
function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms))
}

/** AbortError 여부 판별 */
function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException && err.name === 'AbortError'
  )
}

export function useApi<T>(path: string | null, refreshMs?: number): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(path !== null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  // 진행 중인 요청의 AbortController 참조
  const abortRef = useRef<AbortController | null>(null)

  const fetchData = useCallback(async () => {
    if (path === null) {
      setData(null)
      setLoading(false)
      return
    }

    // 이전 요청 취소
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)

    // 최대 3회 시도 (초기 1회 + 재시도 2회)
    for (let attempt = 0; attempt <= 2; attempt++) {
      try {
        const result = await apiFetch<T>(path, { signal: controller.signal })

        // 언마운트 후 상태 업데이트 방지
        if (controller.signal.aborted) return

        setData(result)
        setError(null)
        setLastUpdated(new Date())
        break
      } catch (err) {
        // 컴포넌트 언마운트 또는 경로 변경으로 인한 취소
        if (controller.signal.aborted) return
        if (isAbortError(err)) return

        // HTTP 오류(4xx/5xx)는 재시도 없이 즉시 실패 처리
        const message = err instanceof Error ? err.message : '알 수 없는 오류'
        if (message.startsWith('HTTP ') || attempt === 2) {
          setError(message)
          break
        }

        // 네트워크 오류: 지수 백오프 후 재시도 (1s, 2s)
        await sleep(1000 * (attempt + 1))
      }
    }

    // 취소된 경우 loading 상태 변경 건너뜀
    if (!controller.signal.aborted) {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    fetchData()

    if (!refreshMs) return

    // 비활성 탭에서는 폴링 중지
    let intervalId: ReturnType<typeof setInterval> | null = null

    function startPolling() {
      if (intervalId) return
      intervalId = setInterval(() => {
        // 탭이 활성 상태일 때만 폴링 실행
        if (document.visibilityState !== 'hidden') {
          fetchData()
        }
      }, refreshMs)
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        // 탭 숨김 시 폴링 중지
        if (intervalId) {
          clearInterval(intervalId)
          intervalId = null
        }
      } else {
        // 탭 복귀 시 즉시 갱신 후 폴링 재개
        fetchData()
        startPolling()
      }
    }

    startPolling()
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      // 언마운트 시 정리
      if (intervalId) clearInterval(intervalId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      abortRef.current?.abort()
    }
  }, [fetchData, refreshMs])

  // isRefreshing: 기존 데이터가 있는 상태에서 재요청 중
  const isRefreshing = data !== null && loading

  return { data, loading, error, lastUpdated, isRefreshing, refetch: fetchData }
}
