import assert from 'node:assert/strict'

import {
  BOT_REPORT_KINDS,
  formatKst,
  kindLabel,
  parseReportBody,
  previewOf,
} from '../src/components/screens/botReportView.ts'

// 종류 — 서버가 허용하는 6가지와 같은 순서·이름
assert.deepEqual(BOT_REPORT_KINDS.map((k) => k.value), ['daily_check', 'weekly_check', 'heatmap', 'whale', 'breakout', 'other'])
assert.equal(kindLabel('heatmap'), '청산 히트맵')
assert.equal(kindLabel('whale'), '고래·온체인')
assert.equal(kindLabel('모르는 종류'), '모르는 종류')

// 시각은 한국 시간으로
assert.equal(formatKst('2026-11-22T00:17:00+00:00'), '11-22 09:17')
assert.equal(formatKst('2026-11-22T15:30:00+00:00'), '11-23 00:30')
assert.equal(formatKst('잘못된 값'), '')

// 문단 — 굵은 글씨와 링크, 줄마다 한 문단
assert.deepEqual(parseReportBody('**근접 (장중)**\n현재가는 [CoinGecko](https://www.coingecko.com/) 기준이에요.'), [
  { type: 'paragraph', inlines: [{ text: '근접 (장중)', bold: true }] },
  {
    type: 'paragraph',
    inlines: [{ text: '현재가는 ' }, { text: 'CoinGecko', href: 'https://www.coingecko.com/' }, { text: ' 기준이에요.' }],
  },
])

// 표 — 구분선 줄은 버리고 첫 줄을 머리글로, 칸 안의 굵은 글씨·링크도 살린다
assert.deepEqual(
  parseReportBody('| 구분 | 11/22 |\n|---|---:|\n| 3일, 아래(롱) | **$57,301 · 44.1M** |\n| 글 | [링크](https://x.com/a/status/1) |'),
  [{
    type: 'table',
    header: [[{ text: '구분' }], [{ text: '11/22' }]],
    rows: [
      [[{ text: '3일, 아래(롱)' }], [{ text: '$57,301 · 44.1M', bold: true }]],
      [[{ text: '글' }], [{ text: '링크', href: 'https://x.com/a/status/1' }]],
    ],
  }],
)

// 목록과 제목
assert.deepEqual(parseReportBody('## 뉴스\n- 첫째\n* 둘째 **강조**\n\n끝'), [
  { type: 'heading', inlines: [{ text: '뉴스' }] },
  { type: 'list', items: [[{ text: '첫째' }], [{ text: '둘째 ' }, { text: '강조', bold: true }]] },
  { type: 'paragraph', inlines: [{ text: '끝' }] },
])

// 링크는 http/https만 건다 — 그 밖의 주소는 글자 그대로
assert.deepEqual(parseReportBody('[위험](javascript:alert(1)) [메일](mailto:a@b.c)'), [
  { type: 'paragraph', inlines: [{ text: '[위험](javascript:alert(1)) [메일](mailto:a@b.c)' }] },
])

// HTML은 해석하지 않는다 — 글자 그대로 남는다(React가 문자로 그린다)
assert.deepEqual(parseReportBody('<script>alert(1)</script>'), [
  { type: 'paragraph', inlines: [{ text: '<script>alert(1)</script>' }] },
])

// 칸 수가 모자란 줄은 빈 칸으로 채우고, 윈도우 줄바꿈도 받는다
assert.deepEqual(parseReportBody('| a | b |\r\n|---|---|\r\n| 1 |'), [
  { type: 'table', header: [[{ text: 'a' }], [{ text: 'b' }]], rows: [[[{ text: '1' }], []]] },
])

// 빈 본문
assert.deepEqual(parseReportBody(''), [])
assert.deepEqual(parseReportBody('\n\n'), [])

// 접힌 카드의 미리보기 — 첫 문단의 글자만, 길면 자른다
assert.equal(previewOf('**굵게** 시작하는 [링크](https://a.b) 문장\n둘째 줄'), '굵게 시작하는 링크 문장')
assert.equal(previewOf('| 표 | 만 |\n|---|---|\n| 있는 | 본문 |'), '')
assert.equal(previewOf('가'.repeat(200)).length, 121) // 120자 + …
