import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, ComposedChart, Bar, ReferenceLine,
  LineChart, Line,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { LEVEL_COLORS, LEVEL_BG, LEVEL_BORDER } from '../../lib/theme'

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

type AssetTab = 'coin' | 'us'

interface MacroHistoryPoint {
  date: string
  close: number
}

interface MacroCurrent {
  price: number
  change_pct: number
}

interface MacroHistoryData {
  ticker: string
  history: MacroHistoryPoint[]
  current: MacroCurrent | null
}

interface MacroApiState {
  data: MacroHistoryData | null
  loading: boolean
  error: string | null
  refetch: () => void
  lastUpdated: Date | null
}

function readAssetTab(): AssetTab {
  const value = new URLSearchParams(window.location.search).get('asset')
  return value === 'us' ? 'us' : 'coin'
}

function formatMacroPrice(ticker: string, price: number) {
  if (ticker === '^TNX') return `${price.toFixed(2)}%`
  if (ticker === 'KRW=X') return `${price.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}원`
  return price.toFixed(2)
}

function MacroCard({ title, data, color }: { title: string; data: MacroHistoryData; color: string }) {
  const chartData = (data.history || []).map(point => ({
    date: point.date?.slice(5),
    close: point.close,
  }))
  const change = data.current?.change_pct ?? 0
  const changeColor = change > 0 ? '#f87171' : change < 0 ? '#60a5fa' : '#94a3b8'

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 4 }}>{title}</div>
          <div style={{ color: '#64748b', fontSize: '0.7rem' }}>{data.ticker}</div>
        </div>
        {data.current && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: '#e2e8f0', fontSize: '1.1rem', fontWeight: 700 }}>
              {formatMacroPrice(data.ticker, data.current.price)}
            </div>
            <div style={{ color: changeColor, fontSize: '0.8rem', fontWeight: 600 }}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)}%
            </div>
          </div>
        )}
      </div>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis
              domain={['auto', 'auto']}
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              width={44}
            />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(v) => [Number(v).toFixed(4), title]}
            />
            <Line type="monotone" dataKey="close" dot={false} stroke={color} strokeWidth={2} name={title} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ color: '#64748b', fontSize: '0.85rem', textAlign: 'center', padding: '56px 0' }}>
          히스토리 데이터 없음
        </div>
      )}
    </Card>
  )
}

function AssetTabs({ asset, onChange }: { asset: AssetTab; onChange: (asset: AssetTab) => void }) {
  const tabs: { value: AssetTab; label: string }[] = [
    { value: 'coin', label: '코인' },
    { value: 'us', label: '미국/환율' },
  ]

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      {tabs.map(tab => {
        const active = asset === tab.value
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onChange(tab.value)}
            style={{
              border: `1px solid ${active ? '#38bdf8' : '#334155'}`,
              background: active ? 'rgba(56,189,248,0.12)' : '#0f172a',
              color: active ? '#e0f2fe' : '#94a3b8',
              borderRadius: 8,
              padding: '8px 12px',
              fontSize: '0.82rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}

function MacroMarketView({ markets }: { markets: { title: string; color: string; api: MacroApiState }[] }) {
  const loading = markets.some(item => item.api.loading && !item.api.data)
  const errored = markets.find(item => item.api.error && !item.api.data)

  if (errored) {
    return <ErrorState error={errored.api.error || '데이터 조회 실패'} onRetry={() => markets.forEach(item => item.api.refetch())} />
  }
  if (loading) return <Skeleton />

  return (
    <div className="grid-3" style={{ gap: 12 }}>
      {markets.map(item => item.api.data && (
        <MacroCard key={item.api.data.ticker} title={item.title} color={item.color} data={item.api.data} />
      ))}
    </div>
  )
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
  const [asset, setAsset] = useState<AssetTab>(() => readAssetTab())
  const coinApi = useApi<MarketData>(asset === 'coin' ? '/api/market-analysis' : null, 300_000)
  const dxyApi = useApi<MacroHistoryData>(asset === 'us' ? `/api/market/macro-history?ticker=${encodeURIComponent('DX-Y.NYB')}` : null, 300_000)
  const tnxApi = useApi<MacroHistoryData>(asset === 'us' ? `/api/market/macro-history?ticker=${encodeURIComponent('^TNX')}` : null, 300_000)
  const krwApi = useApi<MacroHistoryData>(asset === 'us' ? `/api/market/macro-history?ticker=${encodeURIComponent('KRW=X')}` : null, 300_000)

  function changeAsset(next: AssetTab) {
    setAsset(next)
    const url = new URL(window.location.href)
    url.searchParams.set('asset', next)
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`)
  }

  const tabs = <AssetTabs asset={asset} onChange={changeAsset} />

  if (asset === 'us') {
    const macroMarkets = [
      { title: '달러 인덱스', color: '#38bdf8', api: dxyApi },
      { title: '미 10년물', color: '#f59e0b', api: tnxApi },
      { title: '원달러 환율', color: '#22c55e', api: krwApi },
    ]
    const lastUpdated = dxyApi.lastUpdated ?? tnxApi.lastUpdated ?? krwApi.lastUpdated

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <LastUpdated timestamp={lastUpdated} />
        <MacroMarketView markets={macroMarkets} />
      </div>
    )
  }

  const { data, loading, error, refetch, lastUpdated } = coinApi

  if (error && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <ErrorState error={error} onRetry={refetch} />
      </div>
    )
  }
  if (loading || !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <Skeleton />
      </div>
    )
  }

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
      {tabs}
      <LastUpdated timestamp={lastUpdated} />
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
        <div className="grid-4" style={{ gap: 10 }}>
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
