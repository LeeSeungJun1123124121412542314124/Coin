import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'

interface AlertRecord {
  id: number
  timestamp: string
  symbol: string
  alert_level: string
  alert_score: number | null
  final_score: number | null
  message_sent: boolean
}

interface AlertsData {
  alerts: AlertRecord[]
  total: number
}

const LEVEL_COLOR: Record<string, string> = {
  CONFIRMED_HIGH: '#ef4444',
  HIGH: '#f97316',
  LIQUIDATION_RISK: '#a855f7',
  WHALE: '#60a5fa',
}

const LEVEL_LABEL: Record<string, string> = {
  CONFIRMED_HIGH: '확인 경보',
  HIGH: '경보',
  LIQUIDATION_RISK: '청산 위험',
  WHALE: '고래 감지',
}

function formatTs(ts: string): string {
  // "2026-04-10T12:34:56.000000" → "04-10 12:34"
  return ts.slice(5, 16).replace('T', ' ')
}

export function Alerts() {
  const [symbol, setSymbol] = useState<string>('')
  const url = symbol ? `/api/alerts/history?symbol=${symbol}&limit=100` : '/api/alerts/history?limit=100'
  const { data, loading, error, refetch, lastUpdated } = useApi<AlertsData>(url, 60_000)

  if (loading && !data) return <Skeleton />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!data) return null

  const alerts = data.alerts ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <LastUpdated timestamp={lastUpdated} />

      {/* 헤더 + 필터 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ color: '#e2e8f0', fontSize: '1.1rem', fontWeight: 700, margin: 0 }}>알림 히스토리</h2>
          <p style={{ color: '#64748b', fontSize: '0.8rem', margin: '4px 0 0' }}>
            총 {data.total}건
          </p>
        </div>
        <select
          value={symbol}
          onChange={e => setSymbol(e.target.value)}
          style={{
            background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
            borderRadius: 8, padding: '6px 12px', fontSize: '0.875rem', cursor: 'pointer',
          }}
        >
          <option value="">전체 심볼</option>
          <option value="BTC/USDT">BTC/USDT</option>
          <option value="ETH/USDT">ETH/USDT</option>
        </select>
      </div>

      {/* 알림 목록 */}
      {alerts.length === 0 ? (
        <Card>
          <div style={{ color: '#64748b', textAlign: 'center', padding: '24px 0', fontSize: '0.9rem' }}>
            알림 기록이 없습니다.
          </div>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {alerts.map(alert => {
            const color = LEVEL_COLOR[alert.alert_level] ?? '#94a3b8'
            const label = LEVEL_LABEL[alert.alert_level] ?? alert.alert_level
            return (
              <Card key={alert.id}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  {/* 좌측: 레벨 배지 + 심볼 + 시간 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{
                      background: `${color}22`, color, border: `1px solid ${color}55`,
                      borderRadius: 6, padding: '2px 8px', fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap',
                    }}>
                      {label}
                    </span>
                    <div>
                      <div style={{ color: '#e2e8f0', fontSize: '0.875rem', fontWeight: 600 }}>{alert.symbol}</div>
                      <div style={{ color: '#64748b', fontSize: '0.75rem' }}>{formatTs(alert.timestamp)}</div>
                    </div>
                  </div>

                  {/* 우측: 점수 */}
                  <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                    {alert.alert_score != null && (
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#94a3b8', fontSize: '0.7rem' }}>기술 점수</div>
                        <div style={{ color, fontSize: '0.9rem', fontWeight: 700 }}>
                          {alert.alert_score.toFixed(1)}
                        </div>
                      </div>
                    )}
                    {alert.final_score != null && (
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#94a3b8', fontSize: '0.7rem' }}>종합 점수</div>
                        <div style={{ color: '#e2e8f0', fontSize: '0.9rem', fontWeight: 700 }}>
                          {alert.final_score.toFixed(1)}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
