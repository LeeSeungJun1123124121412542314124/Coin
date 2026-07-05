import assert from 'node:assert/strict'

import { describePutcall, toPutcallChartRows } from '../src/components/screens/volumePutcall.ts'

assert.deepEqual(describePutcall(0.66), {
  label: '과열',
  color: '#f87171',
  help: '0.7 미만',
})

assert.deepEqual(describePutcall(1.05), {
  label: '공포',
  color: '#4ade80',
  help: '1.0 초과',
})

assert.deepEqual(describePutcall(null), {
  label: '데이터 없음',
  color: '#64748b',
  help: '-',
})

assert.deepEqual(
  toPutcallChartRows([
    { date: '2026-07-01', total_pc: 0.84, equity_pc: 0.61, index_pc: 1.12 },
    { date: '2026-07-02', total_pc: 0.79, equity_pc: 0.53, index_pc: 0.97 },
  ]),
  [
    { date: '07-01', total: 0.84, equity: 0.61, index: 1.12 },
    { date: '07-02', total: 0.79, equity: 0.53, index: 0.97 },
  ],
)
