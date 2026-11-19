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

// 타임존 표기가 없는 timestamp는 UTC(백엔드 저장 형식)로 해석
function parseTs(ts: string): number {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(ts)
  return new Date(hasZone ? ts : `${ts}Z`).getTime()
}

// KST 날짜 키 'YYYY-MM-DD'
function kstDayKey(ms: number): string {
  const d = new Date(ms + KST_OFFSET_MS)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
}

export function groupAlertsByDay<T extends { timestamp: string }>(
  alerts: T[],
  now: Date,
): { label: string; date: string; items: T[] }[] {
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
      return { label, date, items: byDay.get(key) as T[] }
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
