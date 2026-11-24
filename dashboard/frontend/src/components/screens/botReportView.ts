// 봇 리포트 화면의 순수 함수 — 종류 이름, 시각 표시, 본문(마크다운 일부) 해석
// 스펙: docs/plans/bot-reports-spec-2026-11-24.md

export const BOT_REPORT_KINDS: { value: string; label: string }[] = [
  { value: 'daily_check', label: '일봉 점검' },
  { value: 'weekly_check', label: '주봉 점검' },
  { value: 'heatmap', label: '청산 히트맵' },
  { value: 'whale', label: '고래·온체인' },
  { value: 'breakout', label: '돌파 알림' },
  { value: 'other', label: '기타' },
]

export function kindLabel(kind: string): string {
  return BOT_REPORT_KINDS.find((k) => k.value === kind)?.label ?? kind
}

// UTC ISO 시각 → 한국 시간 "MM-DD HH:mm". 해석할 수 없으면 빈 문자열
export function formatKst(iso: string): string {
  const time = new Date(iso)
  if (Number.isNaN(time.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(time)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
}

export interface Inline {
  text: string
  bold?: boolean
  href?: string
}

export type Block =
  | { type: 'heading'; inlines: Inline[] }
  | { type: 'paragraph'; inlines: Inline[] }
  | { type: 'list'; items: Inline[][] }
  | { type: 'table'; header: Inline[][]; rows: Inline[][][] }

// 굵은 글씨(**…**)와 링크([글](주소))만 해석한다. 링크는 http/https만 — 그 밖은 글자 그대로 둔다
const INLINE = /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g

function parseInlines(text: string): Inline[] {
  const out: Inline[] = []
  let last = 0
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) })
    if (m[1] !== undefined) out.push({ text: m[1], bold: true })
    else out.push({ text: m[2], href: m[3] })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last) })
  return out
}

function splitRow(line: string): string[] {
  return line.replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

const isSeparator = (line: string) => /^\|?[\s:|-]+\|?$/.test(line) && line.includes('-')

// 본문을 블록(제목·문단·목록·표)으로 나눈다. HTML은 해석하지 않으므로 화면에는 글자 그대로 나온다
export function parseReportBody(body: string): Block[] {
  const lines = body.replace(/\r\n/g, '\n').split('\n').map((l) => l.trim())
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line) { i += 1; continue }

    if (line.startsWith('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].startsWith('|')) { tableLines.push(lines[i]); i += 1 }
      const [head, ...rest] = tableLines.filter((l) => !isSeparator(l)).map(splitRow)
      if (!head) continue
      const pad = (cells: string[]) => head.map((_, c) => parseInlines(cells[c] ?? ''))
      blocks.push({ type: 'table', header: head.map(parseInlines), rows: rest.map(pad) })
      continue
    }

    if (/^[-*] /.test(line)) {
      const items: Inline[][] = []
      while (i < lines.length && /^[-*] /.test(lines[i])) { items.push(parseInlines(lines[i].slice(2).trim())); i += 1 }
      blocks.push({ type: 'list', items })
      continue
    }

    const heading = /^#{1,6} +(.*)$/.exec(line)
    blocks.push(heading ? { type: 'heading', inlines: parseInlines(heading[1]) } : { type: 'paragraph', inlines: parseInlines(line) })
    i += 1
  }
  return blocks
}

const PREVIEW_CHARS = 120

// 접힌 카드에 보일 한 줄 — 첫 문단(또는 제목)의 글자만
export function previewOf(body: string): string {
  const first = parseReportBody(body).find((b) => b.type === 'paragraph' || b.type === 'heading')
  if (!first || !('inlines' in first)) return ''
  const text = first.inlines.map((part) => part.text).join('')
  return text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS)}…` : text
}
