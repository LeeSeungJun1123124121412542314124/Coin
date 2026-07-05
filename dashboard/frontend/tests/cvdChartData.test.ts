import assert from 'node:assert/strict'

import { buildCvdChart } from '../src/components/screens/cvdChartData.ts'

const chart = buildCvdChart([
  { date: '0', cvd: 100, close: 6.1 },
  { date: '1', cvd: 140, close: 6.2 },
  { date: '2026-07-05', cvd: 120, close: 6.3 },
  { date: '2026-07-05', cvd: 150, close: 6.4 },
])

assert.deepEqual(
  chart.map(point => point.dateLabel),
  ['0', '1', '07-05', '07-05'],
)

assert.deepEqual(
  chart.map(point => point.xKey),
  ['0:0', '1:1', '2:2026-07-05', '3:2026-07-05'],
)

assert.deepEqual(
  chart.map(point => point.delta),
  [0, 40, -20, 30],
)
