// 사이드바 그룹과 모바일 하단 메뉴 구성
export const NAV_GROUPS: { label: string; paths: string[] }[] = [
  { label: '개요', paths: ['/'] },
  { label: '시장', paths: ['/market', '/liquidity', '/volume'] },
  { label: '파생 · 온체인', paths: ['/spf', '/cvd', '/whale'] },
  { label: '기록 · 검증', paths: ['/research', '/leaderboard', '/alerts'] },
  { label: '학습', paths: ['/learning'] },
]

// 하단 메뉴 앞 4칸 (5번째 칸은 "더보기")
export const MOBILE_PRIMARY: { label: string; path: string }[] = [
  { label: '홈', path: '/' },
  { label: '시장', path: '/market' },
  { label: '파생', path: '/spf' },
  { label: '학습', path: '/learning' },
]

// 경로가 속한 그룹 label (없으면 빈 문자열)
export function groupOf(path: string): string {
  return NAV_GROUPS.find((g) => g.paths.includes(path))?.label ?? ''
}
