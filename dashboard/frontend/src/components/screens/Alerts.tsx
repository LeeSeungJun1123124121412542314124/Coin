import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { C, softBg } from '../../lib/theme'
import { LEVEL_LABEL, countByLevel, formatKst, groupAlertsByDay } from './alertsView'

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

// 레벨 색 — 위험·경보 등 의미 토큰 (상승/하락 색 아님)
const LEVEL_COLOR: Record<string, string> = {
  CONFIRMED_HIGH: C.danger,
  HIGH: C.warn,
  LIQUIDATION_RISK: C.violet,
  WHALE: C.accent,
  STALE_SIGNAL: C.text2,
  MACRO_EVENT: C.info,
}

// 방향 라벨/색 — long=급등(--up), short=급락(--down), neutral=중립(--surface-2 바탕)
const DIR: Record<string, { label: string; color: string; bg: string }> = {
  long: { label: '급등', color: C.up, bg: softBg(C.up, 0.14) },
  short: { label: '급락', color: C.down, bg: softBg(C.down, 0.14) },
  neutral: { label: '중립', color: C.text2, bg: C.surface2 },
}

function DirBadge({ kind, dir, tooltip }: { kind: string; dir: string | null; tooltip?: string }) {
  const d = dir ? DIR[dir] : null
  return (
    <div style={{ textAlign: 'center' }} title={tooltip}>
      <div style={{ color: 'var(--text-3)', fontSize: 11, marginBottom: 3 }}>{kind}</div>
      {d ? (
        <span style={{ background: d.bg, color: d.color, borderRadius: 6, padding: '2px 8px', fontSize: 12, fontWeight: 600 }}>{d.label}</span>
      ) : (
        <span style={{ color: 'var(--text-3)', fontSize: 12 }}>–</span>
      )}
    </div>
  )
}

export function Alerts() {
  const [symbol, setSymbol] = useState<string>('')
  const url = symbol ? `/api/alerts/history?symbol=${symbol}&limit=100` : '/api/alerts/history?limit=100'
  const { data, error, refetch, lastUpdated } = useApi<AlertsData>(url, 60_000)

  // 요약 + 필터 — 뼈대·오류 화면에서도 보여 실패한 심볼에서 빠져나올 수 있게 한다
  const controls = (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
      <span style={{ color: 'var(--text-3)', fontSize: 12 }}>시각은 KST</span>
      {data && (
        <span style={{ color: 'var(--text-2)', fontSize: 14 }}>
          총 <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)', fontWeight: 600 }}>{data.total}</span>건
        </span>
      )}
      <select
        value={symbol}
        onChange={e => setSymbol(e.target.value)}
        aria-label="심볼 필터"
        style={{
          background: 'var(--bg-inset)', border: '1px solid var(--border-strong)', color: 'var(--text)',
          borderRadius: 8, padding: '6px 12px', fontSize: 14, cursor: 'pointer',
        }}
      >
        <option value="">전체 심볼</option>
        <option value="BTC/USDT">BTC/USDT</option>
        <option value="ETH/USDT">ETH/USDT</option>
      </select>
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

  const alerts = data.alerts ?? []
  // 심볼 필터가 적용된 목록 기준으로 건수·날짜 묶음 계산
  const levelCounts = countByLevel(alerts)
  const dayGroups = groupAlertsByDay(alerts, new Date())

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <LastUpdated timestamp={lastUpdated} failed={!!error} />

      {controls}

      {/* 레벨별 건수 칩 */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ color: 'var(--text-3)', fontSize: 12 }}>최근 {alerts.length}건 기준</span>
        {levelCounts.map(({ level, label, count }) => {
          const color = LEVEL_COLOR[level]
          return (
            <span key={level} style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              background: softBg(color, 0.14), color, border: `1px solid ${softBg(color, 0.28)}`,
              borderRadius: 999, padding: '5px 12px', fontSize: 12, fontWeight: 600,
              opacity: count === 0 ? 0.55 : 1,
            }}>
              {label}
              <span style={{ fontFamily: 'var(--font-mono)' }}>{count}</span>
            </span>
          )
        })}
      </div>

      {/* 알림 목록 — 날짜별 묶음 */}
      {alerts.length === 0 ? (
        <Card>
          <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '24px 0', fontSize: 14 }}>
            알림 기록이 없습니다.
          </div>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {dayGroups.map(group => (
            <section key={group.key} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <h3 style={{ margin: 0, display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 15, fontWeight: 600, color: 'var(--text)' }}>
                {group.label}
                {group.label !== group.date && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 400, color: 'var(--text-3)' }}>{group.date}</span>
                )}
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 400, color: 'var(--text-3)' }}>{group.items.length}건</span>
              </h3>
              {group.items.map(alert => {
                const color = LEVEL_COLOR[alert.alert_level] ?? C.text2
                const label = LEVEL_LABEL[alert.alert_level] ?? alert.alert_level
                return (
                  <Card key={alert.id}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                      {/* 좌측: 레벨 배지 + 심볼 + 시간 */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <span style={{
                          background: softBg(color, 0.14), color, border: `1px solid ${softBg(color, 0.28)}`,
                          borderRadius: 6, padding: '2px 8px', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
                        }}>
                          {label}
                        </span>
                        <div>
                          <div style={{ color: 'var(--text)', fontSize: 14, fontWeight: 600 }}>{alert.symbol}</div>
                          <div style={{ color: 'var(--text-3)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{formatKst(alert.timestamp)}</div>
                        </div>
                      </div>

                      {/* 우측: 방향 + 점수 */}
                      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                        <DirBadge kind="종목방향" dir={alert.asset_direction} />
                        <DirBadge
                          kind="시장방향"
                          dir={alert.market_direction}
                          tooltip={
                            alert.market_tilt_confidence != null
                              ? `신뢰도 ${alert.market_tilt_confidence.toFixed(0)} · z ${alert.market_tilt_z?.toFixed(2) ?? '–'}`
                              : undefined
                          }
                        />
                        {alert.alert_score != null && (
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ color: 'var(--text-3)', fontSize: 11 }}>기술 점수</div>
                            <div style={{ color, fontSize: 15, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                              {alert.alert_score.toFixed(1)}
                            </div>
                          </div>
                        )}
                        {alert.final_score != null && (
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ color: 'var(--text-3)', fontSize: 11 }}>종합 점수</div>
                            <div style={{ color: 'var(--text)', fontSize: 15, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                              {alert.final_score.toFixed(1)}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </Card>
                )
              })}
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
