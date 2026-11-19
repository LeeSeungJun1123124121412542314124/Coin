import assert from 'node:assert/strict'

import { countByLevel, formatKst, groupAlertsByDay } from '../src/components/screens/alertsView.ts'

// 기준 시각: 2026-11-19T03:00:00Z = KST 12:00
const now = new Date('2026-11-19T03:00:00Z')
const mk = (timestamp: string, alert_level = 'HIGH') => ({ timestamp, alert_level })

// KST 경계: UTC 15:00(=KST 00:00)부터 새 날, UTC 14:59는 전날
const groups = groupAlertsByDay(
  [
    mk('2026-11-19T00:10:00Z'),
    mk('2026-11-18T15:00:00Z'),
    mk('2026-11-18T14:59:00Z'),
    mk('2026-11-16T10:00:00Z'),
  ],
  now,
)
assert.deepEqual(groups.map((g) => [g.label, g.date, g.items.length]), [
  ['오늘', '11-19', 2],
  ['어제', '11-18', 1],
  ['11-16', '11-16', 1],
])

// 타임존 표기 없는 timestamp는 UTC로 취급 (백엔드 저장 형식)
const naive = groupAlertsByDay([mk('2026-11-18T14:59:00.000000'), mk('2026-11-18T15:00:00.000000')], now)
assert.deepEqual(naive.map((g) => g.label), ['오늘', '어제'])

// 입력이 오래된 순이어도 최신 날짜 먼저, 그룹 안 순서는 입력 순서 유지
const unordered = groupAlertsByDay(
  [mk('2026-11-16T10:00:00Z', 'A'), mk('2026-11-19T01:00:00Z', 'B'), mk('2026-11-19T02:00:00Z', 'C')],
  now,
)
assert.deepEqual(unordered.map((g) => g.label), ['오늘', '11-16'])
assert.deepEqual(unordered[0].items.map((i) => i.alert_level), ['B', 'C'])

assert.deepEqual(groupAlertsByDay([], now), [])

// 레벨 건수: 6개 고정 순서, 없는 레벨 0, 모르는 레벨은 세지 않음
const counts = countByLevel([
  { alert_level: 'HIGH' },
  { alert_level: 'HIGH' },
  { alert_level: 'WHALE' },
  { alert_level: 'UNKNOWN_LEVEL' },
])
assert.deepEqual(counts, [
  { level: 'CONFIRMED_HIGH', label: '확인 경보', count: 0 },
  { level: 'HIGH', label: '경보', count: 2 },
  { level: 'LIQUIDATION_RISK', label: '청산 위험', count: 0 },
  { level: 'WHALE', label: '고래 감지', count: 1 },
  { level: 'STALE_SIGNAL', label: '갱신 필요', count: 0 },
  { level: 'MACRO_EVENT', label: '매크로 이벤트', count: 0 },
])
assert.equal(countByLevel([]).length, 6)

// 카드 시각 KST 변환 (naive는 UTC 취급, offset 있으면 그대로)
assert.equal(formatKst('2026-11-18T15:30:00'), '11-19 00:30')
assert.equal(formatKst('2026-11-18T14:59:00.000000'), '11-18 23:59')
assert.equal(formatKst('2026-11-18T15:30:00Z'), '11-19 00:30')
assert.equal(formatKst('2026-11-19T00:30:00+09:00'), '11-19 00:30')
