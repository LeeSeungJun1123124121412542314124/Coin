const BASE = import.meta.env.VITE_API_URL ?? ''

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem('auth_token') ?? ''
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      ...options?.headers,
    },
  })

  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.detail || body?.error?.message || ''
    } catch {}

    if (res.status === 401) {
      sessionStorage.removeItem('auth_token')
      window.location.reload()
      throw new Error('인증 만료 — 재로그인 필요')
    }

    throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`)
  }
  return res.json()
}
