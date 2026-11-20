import assert from 'node:assert/strict'
import { parseReason } from '../src/components/screens/spfReasons.ts'

// 팩터 이름 → 한국어 이름, 부호 → 방향
assert.deepEqual(parseReason('dxy_13w -2.60'), { label: '달러지수 13주 변화', tone: 'down', value: '−2.60' })
assert.deepEqual(parseReason('rsi14 +1.92'), { label: 'RSI(14)', tone: 'up', value: '+1.92' })
assert.deepEqual(parseReason('sma50_dist -1.63'), { label: '50일 이동평균 이격', tone: 'down', value: '−1.63' })
assert.deepEqual(parseReason('rsi14 +0.00'), { label: 'RSI(14)', tone: 'flat', value: '0.00' })

// 표에 없는 이름은 그대로
assert.deepEqual(parseReason('unknown_factor -0.10'), { label: 'unknown_factor', tone: 'down', value: '−0.10' })

// 형식이 아니면 원문 그대로
assert.deepEqual(parseReason('포지션 변동 미미'), { label: '포지션 변동 미미', tone: 'flat', value: null })
const sentence = 'OI 3일 +3.2% 급등 — 과매수 위험'
assert.deepEqual(parseReason(sentence), { label: sentence, tone: 'flat', value: null })
assert.deepEqual(parseReason(''), { label: '', tone: 'flat', value: null })

console.log('spfReasons tests passed')
