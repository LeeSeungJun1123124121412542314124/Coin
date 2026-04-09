const BASE = import.meta.env.VITE_API_URL ?? ''

export async function apiFetch<T>(path: string): Promise<T> {
  // sessionStorage에서 인증 토큰 조회 후 Authorization 헤더에 첨부
  const token = sessionStorage.getItem('auth_token') ?? ''
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`)
  return res.json()
}
