import { useApi } from '../../hooks/useApi'
import { Card } from './Card'

// 복합 모델 입력(매크로/9팩터) 데이터 신선도 모니터
interface SeriesItem {
  name: string
  last_date: string | null
  days_stale: number | null
}
interface Composite {
  direction: string | null
  n_factors: number
  composite_z: number | null
  ok: boolean
}
interface MacroHealth {
  status: 'ok' | 'warn' | 'stale' | 'no_data'
  cache_age_hours: number | null
  composite: Composite | null
  series: SeriesItem[]
  message?: string
}

const STATUS: Record<string, { label: string; color: string }> = {
  ok: { label: '정상', color: '#4ade80' },
  warn: { label: '주의', color: '#fbbf24' },
  stale: { label: '데이터 정지', color: '#f87171' },
  no_data: { label: '데이터 없음', color: '#64748b' },
}

const NAME_KR: Record<string, string> = {
  close: 'BTC', eth_close: 'ETH', sol_close: 'SOL', net_liquidity: '순유동성',
  dxy: '달러', ust10y: '금리', vix: 'VIX', mvrv: 'MVRV', active_addr: '활성주소',
}

export function MacroHealthCard() {
  const { data } = useApi<MacroHealth>('/api/macro-health', 300_000)
  if (!data) return null
  const st = STATUS[data.status] ?? STATUS.no_data

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>데이터 상태 (방향 모델 입력)</span>
        <span style={{ color: st.color, fontSize: '0.8rem', fontWeight: 700 }}>● {st.label}</span>
      </div>

      {data.status === 'no_data' ? (
        <div style={{ color: '#64748b', fontSize: '0.8rem' }}>{data.message ?? '수집 데이터 없음'}</div>
      ) : (
        <>
          <div style={{ color: '#64748b', fontSize: '0.72rem', marginBottom: 8 }}>
            마지막 수집 {data.cache_age_hours != null ? `${data.cache_age_hours}시간 전` : '–'}
            {data.composite && ` · 복합 ${data.composite.ok ? `정상 (${data.composite.n_factors}/9팩터)` : '산출 불가'}`}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {data.series.map(s => {
              const missing = s.last_date == null
              const stale = s.days_stale != null && s.days_stale > 5
              return (
                <span
                  key={s.name}
                  title={s.last_date ? `${s.last_date} (${s.days_stale}일 전)` : '데이터 없음'}
                  style={{
                    fontSize: '0.7rem', padding: '2px 7px', borderRadius: 6, background: '#1e293b',
                    color: missing ? '#f87171' : stale ? '#fbbf24' : '#94a3b8',
                  }}
                >
                  {NAME_KR[s.name] ?? s.name}
                </span>
              )
            })}
          </div>
        </>
      )}
    </Card>
  )
}
