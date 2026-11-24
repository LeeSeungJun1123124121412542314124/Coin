// 위쪽 메뉴 묶음 5개 — 묶음의 첫 경로가 그 묶음의 대표 화면이고, 나머지는 묶음 안 탭으로 간다
// short는 모바일 아래 탭에 쓰는 짧은 이름
export const NAV_GROUPS: { label: string; short: string; paths: string[] }[] = [
  { label: '홈', short: '홈', paths: ['/'] },
  { label: '시장', short: '시장', paths: ['/market', '/liquidity', '/volume'] },
  { label: '파생 · 온체인', short: '파생', paths: ['/spf', '/cvd', '/whale'] },
  { label: '기록', short: '기록', paths: ['/research', '/alerts', '/bot-reports', '/leaderboard'] },
  { label: '학습', short: '학습', paths: ['/learning'] },
]
