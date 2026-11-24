import assert from 'node:assert/strict'
import { NAV_GROUPS } from '../src/lib/navGroups.ts'

// App의 12개 경로 (App.tsx TABS와 같아야 한다)
const APP_PATHS = [
  '/', '/volume', '/spf', '/research', '/market', '/liquidity',
  '/cvd', '/whale', '/leaderboard', '/alerts', '/bot-reports', '/learning',
]

const all = NAV_GROUPS.flatMap((g) => g.paths)
assert.equal(all.length, 12)
assert.equal(new Set(all).size, 12, '경로 중복')
assert.deepEqual([...all].sort(), [...APP_PATHS].sort())

// 위쪽 메뉴·모바일 아래 탭은 묶음 5개 (docs/plans/light-redesign-spec-2026-11-24.md 5절)
assert.deepEqual(NAV_GROUPS.map((g) => g.label), ['홈', '시장', '파생 · 온체인', '기록', '학습'])
assert.deepEqual(NAV_GROUPS.map((g) => g.short), ['홈', '시장', '파생', '기록', '학습'])
// 묶음을 누르면 가는 대표 화면
assert.deepEqual(NAV_GROUPS.map((g) => g.paths[0]), ['/', '/market', '/spf', '/research', '/learning'])
assert.deepEqual(NAV_GROUPS[3].paths, ['/research', '/alerts', '/bot-reports', '/leaderboard'])

console.log('navGroups ok')
