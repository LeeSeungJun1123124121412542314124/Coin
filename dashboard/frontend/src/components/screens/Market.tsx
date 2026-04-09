import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, ComposedChart, Bar, ReferenceLine,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'

interface Insight {
  level: string
  title: string
  body: string
  icon: string
}

interface KeyIndicator {
  label: string
  value: number
  unit: string
  label2?: string
}

interface VixBtcPoint {
  date: string
  vix: number | null
  btc: number | null
}

interface MarketData {
  insights: Insight[]
  key_indicators: KeyIndicator[]
  vix_btc_history: VixBtcPoint[]
  bot_level: string | null
}

const LEVEL_COLORS: Record<string, string> = {
  critical: '#ef4444',
  warning:  '#f97316',
  bearish:  '#f87171',
  bullish:  '#4ade80',
  neutral:  '#94a3b8',
}

const LEVEL_BG: Record<string, string> = {
  critical: 'rgba(239,68,68,0.10)',
  warning:  'rgba(249,115,22,0.10)',
  bearish:  'rgba(248,113,113,0.08)',
  bullish:  'rgba(74,222,128,0.08)',
  neutral:  'rgba(100,116,139,0.08)',
}

const LEVEL_BORDER: Record<string, string> = {
  critical: 'rgba(239,68,68,0.4)',
  warning:  'rgba(249,115,22,0.3)',
  bearish:  'rgba(248,113,113,0.25)',
  bullish:  'rgba(74,222,128,0.25)',
  neutral:  'rgba(100,116,139,0.2)',
}

function InsightCard({ insight }: { insight: Insight }) {
  const color = LEVEL_COLORS[insight.level] ?? '#94a3b8'
  const bg    = LEVEL_BG[insight.level]    ?? 'rgba(100,116,139,0.08)'
  const border = LEVEL_BORDER[insight.level] ?? 'rgba(100,116,139,0.2)'

  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 10, padding: '12px 14px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: '1rem' }}>{insight.icon}</span>
        <span style={{ color, fontWeight: 600, fontSize: '0.88rem' }}>{insight.title}</span>
      </div>
      <div style={{ color: '#94a3b8', fontSize: '0.80rem', lineHeight: 1.5 }}>
        {insight.body}
      </div>
    </div>
  )
}

function IndicatorChip({ ind }: { ind: KeyIndicator }) {
  return (
    <div style={{ background: '#1e293b', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
      <div style={{ color: '#64748b', fontSize: '0.7rem', marginBottom: 4 }}>{ind.label}</div>
      <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#e2e8f0' }}>
        {ind.value}{ind.unit}
      </div>
      {ind.label2 && (
        <div style={{ color: '#64748b', fontSize: '0.7rem', marginTop: 2 }}>{ind.label2}</div>
      )}
    </div>
  )
}

export function Market() {
  const { data, loading, error, refetch } = useApi<MarketData>('/api/market-analysis', 300_000)

  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (loading || !data) return <Skeleton />

  const { insights, key_indicators, vix_btc_history, bot_level } = data

  // VIX vs BTC — 첫날 대비 % 변화율로 정규화 (같은 스케일 비교)
  const vixBtcRaw = vix_btc_history || []
  const vixBase = vixBtcRaw.find(r => r.vix != null)?.vix
  const btcBase = vixBtcRaw.find(r => r.btc != null)?.btc
  const vixBtcChart = vixBtcRaw.map(r => ({
    date: r.date?.slice(5),
    vix: vixBase && r.vix != null ? +((r.vix / vixBase - 1) * 100).toFixed(1) : null,
    btc: btcBase && r.btc != null ? +((r.btc / btcBase - 1) * 100).toFixed(1) : null,
  }))

  const criticalCount = insights.filter(i => i.level === 'critical').length
  const warningCount  = insights.filter(i => i.level === 'warning').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* 상태 요약 배너 */}
      {(criticalCount > 0 || warningCount > 0) && (
        <div style={{
          background: criticalCount > 0 ? 'rgba(239,68,68,0.12)' : 'rgba(249,115,22,0.10)',
          border: `1px solid ${criticalCount > 0 ? '#ef4444' : '#f97316'}`,
          borderRadius: 8, padding: '10px 16px',
          color: criticalCount > 0 ? '#f87171' : '#fb923c',
          fontWeight: 600, fontSize: '0.88rem',
          display: 'flex', gap: 12, alignItems: 'center',
        }}>
          <span>{criticalCount > 0 ? '🚨' : '⚠️'}</span>
          <span>
            {criticalCount > 0 && `긴급 시그널 ${criticalCount}개`}
            {criticalCount > 0 && warningCount > 0 && ', '}
            {warningCount > 0 && `주의 시그널 ${warningCount}개`}
          </span>
          {bot_level && (
            <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: '#94a3b8' }}>
              봇 레벨: {bot_level}
            </span>
          )}
        </div>
      )}

      {/* 주요 지표 그리드 */}
      {key_indicators.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          {key_indicators.map((ind, i) => (
            <IndicatorChip key={i} ind={ind} />
          ))}
        </div>
      )}

      {/* 인사이트 목록 */}
      {insights.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
            시장 인사이트 ({insights.length}개)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {insights.map((ins, i) => (
              <InsightCard key={i} insight={ins} />
            ))}
          </div>
        </Card>
      )}

      {insights.length === 0 && (
        <Card>
          <div style={{ color: '#64748b', fontSize: '0.85rem', textAlign: 'center', padding: '16px 0' }}>
            현재 특이 시그널 없음 — 정상 시장 상태
          </div>
        </Card>
      )}

      {/* VIX vs BTC 30일 차트 */}
      {vixBtcChart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
            VIX vs BTC 변화율 (30일, 첫날 대비 %)
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={vixBtcChart}>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickFormatter={v => `${v}%`}
                width={40}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v, name) => {
                  const n = v as number
                  return [`${n >= 0 ? '+' : ''}${n}%`, name as string]
                }}
              />
              <ReferenceLine y={0} stroke="#334155" strokeDasharray="3 3" />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
              <Bar dataKey="vix" fill="rgba(248,113,113,0.7)" name="VIX" barSize={8} />
              <Bar dataKey="btc" fill="rgba(245,158,11,0.7)" name="BTC" barSize={8} />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

    </div>
  )
}
