import { useEffect, useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { C, softBg } from '../../lib/theme'
import { fmtFixed } from '../../lib/format'
import {
  LEVEL_LABEL, countByLevel, filterByLevel, formatKst, groupAlertsByDay, summarizeDay, visibleGroups,
} from './alertsView'

interface AlertRecord {
  id: number
  timestamp: string
  symbol: string
  alert_level: string
  alert_score: number | null
  final_score: number | null
  message_sent: boolean
  asset_direction: string | null
  market_direction: string | null
  market_tilt_confidence: number | null
  market_tilt_z: number | null
}

interface AlertsData {
  alerts: AlertRecord[]
  total: number
}

// 걸러 보기·요약 함수용으로 level 필드를 덧붙인 알림 (alert_level과 같은 값)
type Item = AlertRecord & { level: string }

// 레벨 색 — 위험·경보 등 의미 토큰 (상승/하락 색 아님)
const LEVEL_COLOR: Record<string, string> = {
  CONFIRMED_HIGH: C.danger,
  HIGH: C.warn,
  LIQUIDATION_RISK: C.violet,
  WHALE: C.accent,
  STALE_SIGNAL: C.text2,
  MACRO_EVENT: C.info,
}

// 방향 라벨/색 — long=급등(--up ▲), short=급락(--down ▼), neutral=중립(–). 방향은 항상 기호와 함께
const DIR: Record<string, { label: string; color: string; mark: string }> = {
  long: { label: '급등', color: C.up, mark: '▲' },
  short: { label: '급락', color: C.down, mark: '▼' },
  neutral: { label: '중립', color: C.text2, mark: '–' },
}

const SYMBOLS: { label: string; value: string }[] = [
  { label: '전체', value: '' },
  { label: 'BTC', value: 'BTC/USDT' },
  { label: 'ETH', value: 'ETH/USDT' },
]

const PAGE = 8
const MOBILE_QUERY = '(max-width: 767px)'

function Dir({ dir, tooltip }: { dir: string | null; tooltip?: string }) {
  const d = dir ? DIR[dir] : null
  if (!d) return <span style={{ color: 'var(--text-3)' }}>–</span>
  return <span title={tooltip} style={{ color: d.color, fontWeight: 600, whiteSpace: 'nowrap' }}>{d.mark} {d.label}</span>
}

// 화면 폭이 모바일인지 — 표/두 줄 행 중 하나만 그리기 위해 이 파일 안에서만 쓴다
function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY)
    const onChange = () => setMobile(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return mobile
}

function LevelBadge({ alert }: { alert: Item }) {
  const color = LEVEL_COLOR[alert.alert_level] ?? C.text2
  const label = LEVEL_LABEL[alert.alert_level] ?? alert.alert_level
  return (
    <span style={{
      background: softBg(color, 0.14), color, borderRadius: 6, padding: '2px 8px',
      fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  )
}

const marketTip = (a: Item) =>
  a.market_tilt_confidence != null
    ? `신뢰도 ${a.market_tilt_confidence.toFixed(0)} · z ${a.market_tilt_z?.toFixed(2) ?? '–'}`
    : undefined

// 'MM-DD HH:MM' 중 시각만
const timeOnly = (ts: string) => formatKst(ts).slice(6)

// PC: 펼친 날짜를 표로
function AlertTable({ items }: { items: Item[] }) {
  const th = { padding: '0 8px', fontWeight: 500 } as const
  const num = { padding: '0 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' } as const
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', minWidth: 720, borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ color: 'var(--text-3)', fontSize: 12, textAlign: 'left', height: 36 }}>
            <th style={th}>시각</th>
            <th style={th}>종류</th>
            <th style={th}>심볼</th>
            <th style={th}>종목 방향</th>
            <th style={th}>시장 방향</th>
            <th style={{ ...th, textAlign: 'right' }}>기술 점수</th>
            <th style={{ ...th, textAlign: 'right' }}>종합 점수</th>
          </tr>
        </thead>
        <tbody>
          {items.map(a => (
            <tr key={a.id} style={{ height: 44, borderTop: '1px solid var(--line)' }}>
              <td style={{ padding: '0 8px', fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{timeOnly(a.timestamp)}</td>
              <td style={{ padding: '0 8px' }}><LevelBadge alert={a} /></td>
              <td style={{ padding: '0 8px', fontWeight: 600, whiteSpace: 'nowrap' }}>{a.symbol}</td>
              <td style={{ padding: '0 8px' }}><Dir dir={a.asset_direction} /></td>
              <td style={{ padding: '0 8px' }}><Dir dir={a.market_direction} tooltip={marketTip(a)} /></td>
              <td style={num}>{fmtFixed(a.alert_score, 1)}</td>
              <td style={{ ...num, fontSize: 16, fontWeight: 600 }}>{fmtFixed(a.final_score, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// 모바일: 두 줄 행
function AlertRows({ items }: { items: Item[] }) {
  return (
    <div>
      {items.map(a => (
        <div key={a.id} style={{ borderTop: '1px solid var(--line)', padding: '12px 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-2)' }}>{timeOnly(a.timestamp)}</span>
              <LevelBadge alert={a} />
              <span style={{ fontSize: 14, fontWeight: 600 }}>{a.symbol}</span>
            </span>
            <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
              종목 <Dir dir={a.asset_direction} /> · 시장 <Dir dir={a.market_direction} tooltip={marketTip(a)} /> · 기술{' '}
              <span className="v2-nowrap" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{fmtFixed(a.alert_score, 1)}</span>
            </span>
          </div>
          <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종합</span>
            <span className="v2-nowrap" style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 600 }}>{fmtFixed(a.final_score, 1)}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export function Alerts() {
  const [symbol, setSymbol] = useState<string>('')
  const [level, setLevel] = useState<string | null>(null)
  const [shown, setShown] = useState(PAGE)
  // 기본 상태(첫 묶음만 펼침)에서 사용자가 뒤집은 날짜 키
  const [flipped, setFlipped] = useState<Set<string>>(new Set())
  const isMobile = useIsMobile()
  const url = symbol ? `/api/alerts/history?symbol=${symbol}&limit=100` : '/api/alerts/history?limit=100'
  const { data, error, refetch, lastUpdated } = useApi<AlertsData>(url, 60_000)

  const pickSymbol = (v: string) => { setSymbol(v); setShown(PAGE); setFlipped(new Set()) }
  const pickLevel = (v: string | null) => { setLevel(v); setShown(PAGE); setFlipped(new Set()) }
  const flip = (key: string) => setFlipped(prev => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  // 요약 + 심볼 세그먼트 — 뼈대·오류 화면에서도 보여 실패한 심볼에서 빠져나올 수 있게 한다
  const controls = (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
      <span style={{ color: 'var(--text-2)', fontSize: 13 }}>
        {data && (
          <>
            최근 <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)', fontWeight: 600 }}>{data.alerts?.length ?? 0}</span>건 ·{' '}
          </>
        )}
        시각 KST
      </span>
      <div role="group" aria-label="심볼" className="v2-seg" style={{ gridAutoColumns: '56px' }}>
        {SYMBOLS.map(s => (
          <button key={s.value} type="button" className="v2-seg-btn" aria-pressed={symbol === s.value} onClick={() => pickSymbol(s.value)}>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )

  if (!data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {controls}
        {error ? <ErrorState error={error} onRetry={refetch} /> : <Skeleton />}
      </div>
    )
  }

  const alerts: Item[] = (data.alerts ?? []).map(a => ({ ...a, level: a.alert_level }))
  // 칩 건수는 심볼 필터만 적용된 목록 기준, 날짜 묶음은 종류까지 걸러서
  const levelCounts = countByLevel(alerts)
  const filtered = filterByLevel(alerts, level)
  const dayGroups = groupAlertsByDay(filtered, new Date())
  const { groups: shownGroups, hasMore } = visibleGroups(dayGroups, shown)
  const firstKey = dayGroups[0]?.key

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} failed={!!error} />

      {controls}

      {/* 종류 칩 — 전체 + 종류별 건수 */}
      <div role="group" aria-label="종류로 걸러 보기" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button type="button" className="v2-chip" aria-pressed={level === null} onClick={() => pickLevel(null)}>
          전체 <span style={{ fontFamily: 'var(--font-mono)' }}>{alerts.length}</span>
        </button>
        {levelCounts.map(({ level: lv, label, count }) => {
          const color = LEVEL_COLOR[lv]
          const pressed = level === lv
          return (
            <button
              key={lv}
              type="button"
              className="v2-chip"
              aria-pressed={pressed}
              onClick={() => pickLevel(lv)}
              style={pressed ? undefined : { color, background: softBg(color, 0.12), borderColor: softBg(color, 0.3), opacity: count === 0 ? 0.55 : 1 }}
            >
              {label} <span style={{ fontFamily: 'var(--font-mono)' }}>{count}</span>
            </button>
          )
        })}
      </div>

      {/* 알림 목록 — 날짜별 묶음, 첫 묶음만 펼침 */}
      {alerts.length === 0 ? (
        <Card>
          <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '24px 0', fontSize: 14 }}>
            알림 기록이 없습니다.
          </div>
        </Card>
      ) : dayGroups.length === 0 ? (
        <Card>
          <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '24px 0', fontSize: 14 }}>
            이 종류의 알림이 없습니다
          </div>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {shownGroups.map(group => {
            const open = (group.key === firstKey) !== flipped.has(group.key)
            const titleId = `alerts-day-${group.key}`
            if (!open) {
              return (
                <button key={group.key} type="button" className="v2-fold" aria-expanded={false} onClick={() => flip(group.key)}>
                  <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 600 }}>{group.date}</span>
                    <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{summarizeDay(group.items)}</span>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                    <span className="v2-nowrap" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-2)' }}>{group.items.length}건</span>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-2)" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                  </span>
                </button>
              )
            }
            return (
              <section
                key={group.key}
                aria-labelledby={titleId}
                style={{
                  background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-card)',
                  boxShadow: 'var(--shadow-card)', padding: '4px 16px 6px', display: 'flex', flexDirection: 'column',
                }}
              >
                <button
                  type="button"
                  aria-expanded={true}
                  onClick={() => flip(group.key)}
                  style={{
                    minHeight: 48, border: 0, background: 'transparent', color: 'var(--text)', font: 'inherit',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 0, cursor: 'pointer',
                  }}
                >
                  <span id={titleId} style={{ fontSize: 15, fontWeight: 600 }}>
                    <span style={{ fontFamily: 'var(--font-mono)' }}>{group.date}</span>
                    {group.label !== group.date && <span style={{ marginLeft: 6 }}>{group.label}</span>}
                    <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-2)' }}> · {group.items.length}건</span>
                  </span>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-2)" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M6 15l6-6 6 6" /></svg>
                </button>
                {isMobile ? <AlertRows items={group.items} /> : <AlertTable items={group.items} />}
              </section>
            )
          })}

          {hasMore && (
            <button
              type="button"
              onClick={() => setShown(n => n + PAGE)}
              style={{
                alignSelf: 'center', minHeight: 48, padding: '0 28px', borderRadius: 12, border: '1px solid var(--border-strong)',
                background: 'var(--surface-2)', color: 'var(--text)', font: 'inherit', fontSize: 14, cursor: 'pointer',
              }}
            >
              이전 기록 더 보기
            </button>
          )}
        </div>
      )}
    </div>
  )
}
