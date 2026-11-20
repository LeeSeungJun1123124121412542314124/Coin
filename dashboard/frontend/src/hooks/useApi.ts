import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../lib/api'
import { deriveApiState, type ApiFailure, type ApiResult } from './apiState.ts'

interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
  isRefreshing: boolean
  refetch: () => void
}

/** 지정 ms 동안 대기 — abort 신호 수신 시 즉시 거부 */
function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const id = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(id)
      reject(new DOMException('', 'AbortError'))
    }, { once: true })
  })
}

/** AbortError 여부 판별 */
function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException && err.name === 'AbortError'
  )
}

export function useApi<T>(path: string | null, refreshMs?: number): UseApiResult<T> {
  // 결과·실패는 받은 주소와 함께 보관 — 화면에 내놓는 값은 deriveApiState가 지금 주소 기준으로 계산
  const [result, setResult] = useState<ApiResult<T> | null>(null)
  const [failure, setFailure] = useState<ApiFailure | null>(null)
  const [fetching, setFetching] = useState(false)

  // 진행 중인 요청의 AbortController 참조
  const abortRef = useRef<AbortController | null>(null)
  // 데이터를 받은 주소 — 같은 주소 재조회(주기 갱신·탭 복귀)인지 가른다
  const loadedPathRef = useRef<string | null>(null)

  const fetchData = useCallback(async () => {
    // 이전 요청 취소
    abortRef.current?.abort()
    if (path === null) return

    const controller = new AbortController()
    abortRef.current = controller

    // 데이터가 없는 조회는 이전 실패를 지우고 로딩으로. 같은 주소 재조회는 결과가 나올 때까지 그대로 둔다
    if (loadedPathRef.current !== path) setFailure(null)
    setFetching(true)

    // 최대 3회 시도 (초기 1회 + 재시도 2회)
    for (let attempt = 0; attempt <= 2; attempt++) {
      try {
        const data = await apiFetch<T>(path, { signal: controller.signal })

        // 언마운트 후 상태 업데이트 방지
        if (controller.signal.aborted) return

        loadedPathRef.current = path
        setResult({ path, data, at: new Date() })
        setFailure(null)
        break
      } catch (err) {
        // 컴포넌트 언마운트 또는 경로 변경으로 인한 취소
        if (controller.signal.aborted) return
        if (isAbortError(err)) return

        // HTTP 오류(4xx/5xx)는 재시도 없이 즉시 실패 처리
        const message = err instanceof Error ? err.message : '알 수 없는 오류'
        if (message.startsWith('HTTP ') || attempt === 2) {
          setFailure({ path, message })
          break
        }

        // 네트워크 오류: 지수 백오프 후 재시도 (1s, 2s)
        await sleep(1000 * (attempt + 1), controller.signal)
      }
    }

    // 취소된 경우 상태 변경 건너뜀
    if (!controller.signal.aborted) {
      setFetching(false)
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

  return { ...deriveApiState(path, result, failure, fetching), refetch: fetchData }
}
