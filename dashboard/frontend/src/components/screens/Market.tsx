import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { useIsMobile } from '../../hooks/useIsMobile'
import { Card } from '../shared/Card'
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, ComposedChart, Bar, ReferenceLine,
  LineChart, Line,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { AssetTabs } from '../shared/AssetTabs'
import { readAssetTab, replaceAssetTab, type AssetTab } from '../shared/assetTabUtils'
import { C, LEVEL_COLORS, LEVEL_BG, changeColor, changeArrow, softBg } from '../../lib/theme'
import { fmtFixed, fmtSignedPct } from '../../lib/format'

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

function formatMacroPrice(ticker: string, price: number) {
  if (ticker === '^TNX') return `${fmtFixed(price, 2)}%`
  if (ticker === 'KRW=X') return `${fmtFixed(price, 2)}원`
  return fmtFixed(price, 2)
}

function MacroCard({ title, data, color }: { title: string; data: MacroHistoryData; color: string }) {
  const chartData = (data.history || []).map(point => ({
    date: point.date?.slice(5),
    close: point.close,
  }))
  const change = data.current?.change_pct ?? 0
  const changeClr = changeColor(change)

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 4 }}>{title}</div>
          <div style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>{data.ticker}</div>
        </div>
        {data.current && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: 'var(--text)', fontSize: '1.1rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
              {formatMacroPrice(data.ticker, data.current.price)}
            </div>
            <div className="v2-nowrap" style={{ color: changeClr, fontSize: '0.8rem', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {changeArrow(change)} {fmtSignedPct(change)}
            </div>
          </div>
        )}
      </div>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis
              domain={['auto', 'auto']}
              tick={{ fill: C.text2, fontSize: 11 }}
              width={48}
            />
            <Tooltip
              contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
              labelStyle={{ color: C.text2 }}
              formatter={(v) => [fmtFixed(Number(v), 4), title]}
            />
            <Line type="monotone" dataKey="close" dot={false} stroke={color} strokeWidth={2} name={title} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ color: 'var(--text-3)', fontSize: '0.85rem', textAlign: 'center', padding: '56px 0' }}>
          히스토리 데이터 없음
        </div>
      )}
    </Card>
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


// 서버 level 값을 읽는 말로 — 방향 레벨은 ▲▼를 함께 붙인다
const LEVEL_TAG: Record<string, string> = {
  critical: '위험',
  warning: '주의',
  bearish: '▼ 약세',
  bullish: '▲ 강세',
  neutral: '중립',
}

function InsightCard({ insight }: { insight: Insight }) {
  const color = LEVEL_COLORS[insight.level] ?? C.text2
  const bg = LEVEL_BG[insight.level] ?? softBg(C.text2, 0.08)

  return (
    <div style={{ borderTop: '1px solid var(--line)', padding: '12px 0 8px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="v2-nowrap" style={{ flex: 'none', fontSize: 12, fontWeight: 600, borderRadius: 6, padding: '3px 8px', background: bg, color }}>
          {LEVEL_TAG[insight.level] ?? insight.level}
        </span>
        <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 15 }}>{insight.title}</span>
      </div>
      <div style={{ color: 'var(--text-2)', fontSize: 13, lineHeight: 1.5 }}>{insight.body}</div>
    </div>
  )
}

// 방향이 있는 지표(변화율)는 ▲▼와 방향 색을 쓴다
const SIGNED_INDICATORS = ['김프', 'OI 3일']

function indicatorValue(ind: KeyIndicator): { text: string; color: string } {
  if (SIGNED_INDICATORS.includes(ind.label)) {
    return { text: `${changeArrow(ind.value)} ${fmtSignedPct(ind.value)}`, color: changeColor(ind.value) }
  }
  const digits = ind.unit === 'pt' ? 0 : ind.label === '펀딩비' ? 4 : ind.label === 'BTC 도미넌스' ? 1 : 2
  return { text: `${fmtFixed(ind.value, digits)}${ind.unit}`, color: 'var(--text)' }
}

export function Market() {
  const isMobile = useIsMobile()
  const [asset, setAsset] = useState<AssetTab>(() => readAssetTab(['coin', 'us']))
  const coinApi = useApi<MarketData>(asset === 'coin' ? '/api/market-analysis' : null, 300_000)
  const dxyApi = useApi<MacroHistoryData>(asset === 'us' ? `/api/market/macro-history?ticker=${encodeURIComponent('DX-Y.NYB')}` : null, 300_000)
  const tnxApi = useApi<MacroHistoryData>(asset === 'us' ? `/api/market/macro-history?ticker=${encodeURIComponent('^TNX')}` : null, 300_000)
  const krwApi = useApi<MacroHistoryData>(asset === 'us' ? `/api/market/macro-history?ticker=${encodeURIComponent('KRW=X')}` : null, 300_000)

  function handleAssetChange(next: AssetTab) {
    setAsset(next)
    replaceAssetTab(next)
  }

  const tabs = <AssetTabs asset={asset} allowedTabs={['coin', 'us']} onChange={handleAssetChange} />

  if (asset === 'us') {
    const macroMarkets = [
      { title: '달러 인덱스', color: C.info, api: dxyApi },
      { title: '미 10년물', color: C.accent, api: tnxApi },
      { title: '원달러 환율', color: C.violet, api: krwApi },
    ]
    const lastUpdated = dxyApi.lastUpdated ?? tnxApi.lastUpdated ?? krwApi.lastUpdated

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <LastUpdated timestamp={lastUpdated} failed={!!(dxyApi.error || tnxApi.error || krwApi.error)} />
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

  // 주의 신호 = 서버가 warning·critical로 표시한 인사이트
  const alertCount = insights.filter(i => i.level === 'warning' || i.level === 'critical').length
  const bannerColor = alertCount > 0 ? C.warn : C.ok

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {tabs}
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      {/* 상태 요약 배너 */}
      <div role="status" style={{
        minHeight: 56, boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        padding: '10px 14px', borderRadius: 14,
        background: softBg(bannerColor, 0.08), border: `1px solid ${softBg(bannerColor, 0.3)}`,
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text)', fontSize: 16, fontWeight: 700 }}>
          {alertCount > 0 ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={bannerColor} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l9 16H3zM12 10v4M12 17h.01" /></svg>
          ) : (
            <span aria-hidden="true" style={{ color: bannerColor, fontSize: 18 }}>✓</span>
          )}
          {alertCount > 0 ? `주의 신호 ${alertCount}건` : '주의 신호 없음'}
        </span>
        {bot_level && (
          <span className="v2-nowrap" style={{ fontSize: 13, color: 'var(--text-2)' }}>
            봇 레벨 <span style={{ fontWeight: 700, color: 'var(--text)' }}>{bot_level}</span>
          </span>
        )}
      </div>

      {/* 핵심 지표 목록 — PC는 2열 */}
      {key_indicators.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text)', fontSize: 15, fontWeight: 600, marginBottom: 4 }}>핵심 지표</div>
          <div className="v2-list" style={isMobile ? undefined : { display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 32 }}>
            {key_indicators.map((ind, i) => {
              const v = indicatorValue(ind)
              return (
                <div key={i} className="v2-row">
                  <span className="v2-nowrap">{ind.label}</span>
                  <span>
                    {ind.label2 && <span className="v2-note" style={{ color: 'var(--text-2)' }}>{ind.label2}</span>}
                    <span style={{ color: v.color }}>{v.text}</span>
                  </span>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* 인사이트 목록 */}
      {insights.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text)', fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
            시장 인사이트 <span style={{ color: 'var(--text-3)', fontWeight: 500, fontSize: 13 }}>{insights.length}개</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {insights.map((ins, i) => (
              <InsightCard key={i} insight={ins} />
            ))}
          </div>
        </Card>
      )}

      {insights.length === 0 && (
        <Card>
          <div style={{ color: 'var(--text-3)', fontSize: '0.85rem', textAlign: 'center', padding: '16px 0' }}>
            현재 특이 시그널 없음 — 정상 시장 상태
          </div>
        </Card>
      )}

      {/* VIX vs BTC 30일 차트 */}
      {vixBtcChart.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
            VIX vs BTC 변화율 (30일, 첫날 대비 %)
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={vixBtcChart}>
              <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fill: C.text2, fontSize: 11 }}
                tickFormatter={v => `${v}%`}
                width={44}
              />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                labelStyle={{ color: C.text2 }}
                formatter={(v, name) => {
                  const n = v as number
                  return [fmtSignedPct(n, 1), name as string]
                }}
              />
              <ReferenceLine y={0} stroke={C.borderStrong} strokeDasharray="3 3" />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
              <Bar dataKey="vix" fill={softBg(C.neutralSeries, 0.85)} name="VIX" barSize={8} />
              <Bar dataKey="btc" fill={softBg(C.accent, 0.85)} name="BTC" barSize={8} />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

    </div>
  )
}
