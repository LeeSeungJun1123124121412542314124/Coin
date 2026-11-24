import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { C, LEVEL_COLORS, changeColor, changeArrow, softBg } from '../src/lib/theme.ts'

// index.css의 :root 블록에서 변수 값을 읽는다
const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const root = css.match(/:root\s*\{([^}]*)\}/)?.[1] ?? ''
const kebab = (k: string) => k.replace(/[A-Z0-9]/g, (m) => '-' + m.toLowerCase())

for (const [key, hex] of Object.entries(C)) {
  const m = root.match(new RegExp(`--${kebab(key)}: *([^;]+);`))
  assert.ok(m, `--${kebab(key)} 가 :root에 없음`)
  assert.equal(m[1].trim().toLowerCase(), hex.toLowerCase(), `--${kebab(key)} 값 불일치`)
}

// 밝은 테마(docs/plans/light-redesign-spec-2026-11-24.md 4절): 아이보리 바탕, 먹색 글자, 강세는 초록
assert.equal(C.bg, '#F8F6F1')
assert.equal(C.text, '#25231F')
assert.match(root, /color-scheme: *light;/)
assert.equal(LEVEL_COLORS.bullish, C.ok)
assert.equal(LEVEL_COLORS.critical, C.danger)

for (const name of ['link', 'link-hover', 'shadow-card', 'radius-card', 'font-sans', 'font-mono', 'gold', 'gold-on-ink', 'on-ink-2', 'up-on-ink', 'down-on-ink']) {
  assert.match(root, new RegExp(`--${name}:`), `--${name} 없음`)
}

assert.equal(changeColor(1.2), C.up)
assert.equal(changeColor(-0.1), C.down)
assert.equal(changeColor(0), C.text2)
assert.equal(changeColor(null), C.text2)
assert.equal(changeColor(undefined), C.text2)
assert.equal(changeColor(NaN), C.text2)

assert.equal(changeArrow(3), '▲')
assert.equal(changeArrow(-3), '▼')
assert.equal(changeArrow(0), '–')
assert.equal(changeArrow(null), '–')

assert.equal(softBg('#F2606A', 0.14), 'rgba(242,96,106,0.14)')

console.log('themeTokens ok')
