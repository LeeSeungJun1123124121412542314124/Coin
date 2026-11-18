import assert from 'node:assert/strict'

import {
  PHASE_LABELS,
  formatUsdtKrw,
  toCandleSeries,
  toCloudBands,
  toLineSeries,
  toPivotLine,
  toWyckoffMarkers,
} from '../src/components/learning/learningChartData.ts'
import { INTERVALS, INTERVAL_LABELS, isIntraday } from '../src/components/learning/learningShared.ts'

// 캔들: ms -> 초
assert.deepEqual(
  toCandleSeries([{ open_time: 1_700_000_000_000, open: 1, high: 3, low: 0.5, close: 2, volume: 10 }]),
  [{ time: 1_700_000_000, open: 1, high: 3, low: 0.5, close: 2 }],
)

// 선: null 제외 + ms -> 초
const ich = [
  { time: 1000, tenkan: null, kijun: 5, senkou_a: 10, senkou_b: 8, chikou: null },
  { time: 2000, tenkan: 4, kijun: null, senkou_a: 7, senkou_b: 9, chikou: 3 },
  { time: 3000, tenkan: 6, kijun: 6, senkou_a: null, senkou_b: 9, chikou: null },
  { time: 4000, tenkan: 6, kijun: 6, senkou_a: 5, senkou_b: null, chikou: null },
]
assert.deepEqual(toLineSeries(ich, 'tenkan'), [{ time: 2, value: 4 }, { time: 3, value: 6 }, { time: 4, value: 6 }])
assert.deepEqual(toLineSeries(ich, 'chikou'), [{ time: 2, value: 3 }])

// 구름: 두 값이 모두 있는 행만, top/bottom/bullish
assert.deepEqual(toCloudBands(ich), [
  { time: 1, top: 10, bottom: 8, bullish: true },
  { time: 2, top: 9, bottom: 7, bullish: false },
])

// 와이코프 마커: 시간 오름차순, 강 접두, 같은 봉 두 마커 허용
const markers = toWyckoffMarkers({
  volume_spikes: [],
  current_box: null,
  candidates: [
    { time: 5000, type: 'upthrust', strong: false, box_high: 2, box_low: 1 },
    { time: 2000, type: 'spring', strong: true, box_high: 2, box_low: 1 },
    { time: 5000, type: 'spring', strong: false, box_high: 2, box_low: 1 },
  ],
})
assert.equal(markers.length, 3)
assert.deepEqual(markers.map(m => m.time), [2, 5, 5])
assert.equal(markers[0].text, '강 스프링')
assert.equal(markers[0].position, 'belowBar')
assert.equal(markers[0].shape, 'arrowUp')
const ut = markers.find(m => m.text === '업스러스트')!
assert.equal(ut.position, 'aboveBar')
assert.equal(ut.shape, 'arrowDown')
assert.equal(toWyckoffMarkers({ volume_spikes: [], current_box: null, candidates: [] }).length, 0)

// 지그재그 피벗
assert.deepEqual(
  toPivotLine([{ time: 3000, price: 9, kind: 'high' }, { time: 1000, price: 4, kind: 'low' }]),
  [{ time: 1, value: 4 }, { time: 3, value: 9 }],
)

// 금액 표기
assert.equal(formatUsdtKrw(1234.56, 1400), '1,234.56 USDT (≈ 1,728,384원)')
assert.equal(formatUsdtKrw(1234.56, null), '1,234.56 USDT')
assert.equal(formatUsdtKrw(10, null), '10.00 USDT')

assert.equal(PHASE_LABELS.accumulation, '매집')
assert.equal(PHASE_LABELS.unclear, '불명확')

// 시간 단위: 토글 순서·라벨·분봉 여부
assert.deepEqual(INTERVALS, ['1h', '4h', '1d', '1w', '1M'])
assert.deepEqual(INTERVALS.map(i => INTERVAL_LABELS[i]), ['1시간봉', '4시간봉', '일봉', '주봉', '월봉'])
assert.deepEqual(INTERVALS.map(isIntraday), [true, true, false, false, false])

console.log('learningChartData tests passed')
