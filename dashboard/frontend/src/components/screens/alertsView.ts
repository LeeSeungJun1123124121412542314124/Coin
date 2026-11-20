// 알림히스토리 데이터 가공 (순수 함수) — KST 날짜 묶음, 레벨 건수

// 레벨 표시 순서(고정)와 한글 라벨
export const LEVEL_LABEL: Record<string, string> = {
  CONFIRMED_HIGH: '확인 경보',
  HIGH: '경보',
  LIQUIDATION_RISK: '청산 위험',
  WHALE: '고래 감지',
  STALE_SIGNAL: '갱신 필요',
  MACRO_EVENT: '매크로 이벤트',
}

const KST_OFFSET_MS = 9 * 60 * 60 * 1000
const DAY_MS = 24 * 60 * 60 * 1000

// 타임존 표기가 없는 timestamp는 UTC로 해석 (SQLite datetime('now')의 "YYYY-MM-DD HH:MM:SS" 공백 형식 포함)
function parseTs(ts: string): number {
  const iso = ts.trim().replace(' ', 'T')
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(iso)
  return new Date(hasZone ? iso : `${iso}Z`).getTime()
}

const pad2 = (n: number) => String(n).padStart(2, '0')

// KST(UTC+9) 시각 구성요소 — 날짜 묶음과 카드 시각 표시가 같은 변환을 쓴다
function kstParts(ms: number) {
  const d = new Date(ms + KST_OFFSET_MS)
  return {
    year: d.getUTCFullYear(),
    month: pad2(d.getUTCMonth() + 1),
    day: pad2(d.getUTCDate()),
    hour: pad2(d.getUTCHours()),
    minute: pad2(d.getUTCMinutes()),
  }
}

// KST 날짜 키 'YYYY-MM-DD'
function kstDayKey(ms: number): string {
  const p = kstParts(ms)
  return `${p.year}-${p.month}-${p.day}`
}

// 카드 표시용 KST 'MM-DD HH:MM'
export function formatKst(ts: string): string {
  const p = kstParts(parseTs(ts))
  return `${p.month}-${p.day} ${p.hour}:${p.minute}`
}

export function groupAlertsByDay<T extends { timestamp: string }>(
  alerts: T[],
  now: Date,
): { key: string; label: string; date: string; items: T[] }[] {
  const todayKey = kstDayKey(now.getTime())
  const yesterdayKey = kstDayKey(now.getTime() - DAY_MS)
  const byDay = new Map<string, T[]>()
  for (const a of alerts) {
    const key = kstDayKey(parseTs(a.timestamp))
    const list = byDay.get(key)
    if (list) list.push(a)
    else byDay.set(key, [a])
  }
  return [...byDay.keys()]
    .sort()
    .reverse()
    .map((key) => {
      const date = key.slice(5)
      const label = key === todayKey ? '오늘' : key === yesterdayKey ? '어제' : date
      return { key, label, date, items: byDay.get(key) as T[] }
    })
}

export function countByLevel(
  alerts: { alert_level: string }[],
): { level: string; label: string; count: number }[] {
  return Object.entries(LEVEL_LABEL).map(([level, label]) => ({
    level,
    label,
    count: alerts.filter((a) => a.alert_level === level).length,
  }))
}

// 종류로 걸러 보기 — null이면 전부
export function filterByLevel<T extends { level: string }>(alerts: T[], level: string | null): T[] {
  return level === null ? alerts : alerts.filter((a) => a.level === level)
}

// 날짜 한 줄 요약 — LEVEL_LABEL 순서로 "확인 경보 1 · 경보 1"
export function summarizeDay(alerts: { level: string }[]): string {
  return Object.entries(LEVEL_LABEL)
    .map(([level, label]) => ({ label, count: alerts.filter((a) => a.level === level).length }))
    .filter((x) => x.count > 0)
    .map((x) => `${x.label} ${x.count}`)
    .join(' · ')
}

// 앞에서 shown개만 보이고, 남은 게 있으면 hasMore
export function visibleGroups<T>(groups: T[], shown: number): { groups: T[]; hasMore: boolean } {
  return { groups: groups.slice(0, shown), hasMore: groups.length > shown }
}
