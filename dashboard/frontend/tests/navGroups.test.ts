import assert from 'node:assert/strict'
import { NAV_GROUPS, MOBILE_PRIMARY, groupOf } from '../src/lib/navGroups.ts'

// App의 12개 경로 (App.tsx TABS와 같아야 한다)
const APP_PATHS = [
  '/', '/volume', '/spf', '/research', '/market', '/liquidity',
  '/cvd', '/whale', '/leaderboard', '/alerts', '/bot-reports', '/learning',
]

const all = NAV_GROUPS.flatMap((g) => g.paths)
assert.equal(all.length, 12)
assert.equal(new Set(all).size, 12, '경로 중복')
assert.deepEqual([...all].sort(), [...APP_PATHS].sort())

assert.equal(MOBILE_PRIMARY.length, 4)
for (const m of MOBILE_PRIMARY) assert.ok(all.includes(m.path), `${m.path} 가 NAV_GROUPS에 없음`)

assert.equal(groupOf('/whale'), '파생 · 온체인')
assert.equal(groupOf('/'), '개요')
assert.equal(groupOf('/nope'), '')

assert.equal(groupOf('/bot-reports'), '기록 · 검증')

console.log('navGroups ok')
