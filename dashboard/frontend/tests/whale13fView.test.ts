import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('../src/components/screens/Whale.tsx', import.meta.url)),
  'utf8',
)

assert.match(source, /\/api\/whale\/us-13f-holdings/)
assert.match(source, /기관 보유 \(13F\)/)
assert.match(source, /분기 · 45일 지연/)
assert.match(source, /기관 보유 데이터가 없습니다/)

console.log('whale13fView tests passed')
