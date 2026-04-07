import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../lib/api'

interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useApi<T>(path: string | null, refreshMs?: number): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(path !== null)
  const [error, setError] = useState<string | null>(null)

  const fetch_ = useCallback(async () => {
    if (path === null) {
      setData(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await apiFetch<T>(path)
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    fetch_()
    if (refreshMs) {
      const id = setInterval(fetch_, refreshMs)
      return () => clearInterval(id)
    }
  }, [fetch_, refreshMs])

  return { data, loading, error, refetch: fetch_ }
}
