import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, Legend,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { AssetTabs } from '../shared/AssetTabs'
import { readAssetTab, replaceAssetTab, type AssetTab } from '../shared/assetTabUtils'
import { GaugeChart } from '../shared/GaugeChart'
import { describePutcall, toPutcallChartRows, type PutcallRecord, type PutcallSeries } from './volumePutcall'
import { resolveUsVolumeSections } from './volumeUsState'
import { C, changeColor, changeArrow } from '../../lib/theme'
import { fmtFixed, fmtSignedPct } from '../../lib/format'

interface VolumeData {
  current: {
    upbit_krw: number | null
    bithumb_krw: number | null
    total_krw: number | null
  }
  avg_30d: {
    upbit_krw: number | null
    bithumb_krw: number | null
  }
  history: Array<{
    date: string
    upbit_krw: number | null
    bithumb_krw: number | null
    crypto_ratio: number | null
  }>
}

interface WeeklyData {
  weeks: Array<{
    week: string
    upbit_krw: number
    bithumb_krw: number
    total_krw: number
  }>
}

interface RsiData {
  rsi: Array<{ date: string; rsi: number }>
}

interface FearGreedHistory {
  history: Array<{ date: string; value: number; label: string }>
}

interface StockFearGreedData {
  value: number | null
  rating: string | null
  updated_at: string | null
  stale: boolean
}

interface KrMarketVolumeData {
  stale: boolean
  records: Array<{
    date: string
    kospi_value: number | null
    kosdaq_value: number | null
  }>
}

interface PutcallData {
  stale: boolean
  records: PutcallRecord[]
}

// 업비트/빗썸 점유율 — 얇은 막대와 12px 라벨
function VolumeRatio({ upbit, bithumb }: { upbit: number | null; bithumb: number | null }) {
  const total = (upbit ?? 0) + (bithumb ?? 0)
  if (total === 0) return null
  const upbitPct = (upbit ?? 0) / total * 100
  const bithumbPct = (bithumb ?? 0) / total * 100
  return (
    <div style={{ borderTop: '1px solid var(--line)', padding: '10px 0 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
        <span style={{ fontSize: 14, color: 'var(--text-2)' }}>합산 점유율</span>
        <span className="v2-nowrap" style={{ fontSize: 13, color: 'var(--text-2)' }}>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{fmtFixed(upbitPct, 1)}%</span>
          {' : '}
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{fmtFixed(bithumbPct, 1)}%</span>
        </span>
      </div>
      <div
        role="img"
        aria-label={`업비트 ${fmtFixed(upbitPct, 1)}퍼센트, 빗썸 ${fmtFixed(bithumbPct, 1)}퍼센트`}
        style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', gap: 2 }}
      >
        <div style={{ width: `${upbitPct}%`, background: 'var(--accent)' }} />
        <div style={{ width: `${bithumbPct}%`, background: 'var(--neutral-series)' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-2)' }}>
        <span>업비트</span>
        <span>빗썸</span>
      </div>
    </div>
  )
}

// RSI 상태 — 70 이상 과매수, 30 이하 과매도 (RSI 차트의 기준선과 같다)
function rsiState(value: number): { label: string; color: string } {
  if (value >= 70) return { label: '과매수', color: 'var(--warn)' }
  if (value <= 30) return { label: '과매도', color: 'var(--ok)' }
  return { label: '중립', color: 'var(--text-2)' }
}

function StockFearGreedView({ data }: { data: StockFearGreedData }) {
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 4 }}>CNN Fear & Greed</div>
          <div style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>
            {data.updated_at ? new Date(data.updated_at).toLocaleString('ko-KR') : '데이터 없음'}
            {data.stale && <span style={{ color: 'var(--warn)', marginLeft: 8 }}>갱신 확인 필요</span>}
          </div>
        </div>
        <div style={{ color: 'var(--text)', fontSize: '0.92rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
          {data.rating ?? '-'}
        </div>
      </div>
      {data.value != null ? (
        <GaugeChart value={Math.round(data.value)} label="Stock F&G" size={180} />
      ) : (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '56px 0', fontSize: '0.85rem' }}>
          데이터가 없습니다
        </div>
      )}
    </Card>
  )
}

function PutcallView({ data }: { data: PutcallData }) {
  const [series, setSeries] = useState<PutcallSeries>('equity')
  const latest = data.records.at(-1)
  const equity = latest?.equity_pc ?? null
  const signal = describePutcall(equity)
  const chartData = toPutcallChartRows(data.records)
  const seriesLabel: Record<PutcallSeries, string> = {
    equity: 'Equity',
    total: 'Total',
    index: 'Index',
  }

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 14 }}>
        <div>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 4 }}>CBOE Put/Call</div>
          <div style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>
            {latest?.date ?? '데이터 없음'}
            {data.stale && <span style={{ color: 'var(--warn)', marginLeft: 8 }}>갱신 확인 필요</span>}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ color: signal.color, fontSize: '1.35rem', fontWeight: 800 }}>
            {equity != null ? fmtFixed(equity, 2) : '-'}
          </div>
          <div style={{ color: signal.color, fontSize: '0.75rem', fontWeight: 700 }}>
            {signal.label} · {signal.help}
          </div>
        </div>
      </div>

      <div className="v2-seg" role="group" aria-label="Put/Call 종류" style={{ marginBottom: 12 }}>
        {(['equity', 'total', 'index'] as PutcallSeries[]).map(item => (
          <button
            key={item}
            type="button"
            className="v2-seg-btn"
            aria-pressed={series === item}
            onClick={() => setSeries(item)}
          >
            {seriesLabel[item]}
          </button>
        ))}
      </div>

      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={190}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: C.text2, fontSize: 11 }} width={38} domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
              labelStyle={{ color: C.text2 }}
              formatter={(v) => [typeof v === 'number' ? fmtFixed(v, 2) : v, seriesLabel[series]]}
            />
            <ReferenceLine y={0.7} stroke={C.warn} strokeDasharray="3 3" />
            <ReferenceLine y={1.0} stroke={C.ok} strokeDasharray="3 3" />
            <Line type="monotone" dataKey={series} stroke={C.accent} dot={false} strokeWidth={2} name={seriesLabel[series]} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '48px 0', fontSize: '0.85rem' }}>
          데이터가 없습니다
        </div>
      )}
    </Card>
  )
}

function KrMarketVolumeView({ data }: { data: KrMarketVolumeData }) {
  const chartData = data.records
    .filter(record => record.kospi_value != null && record.kosdaq_value != null)
    .map(record => ({
      date: record.date.slice(5),
      kospi: record.kospi_value as number,
      kosdaq: record.kosdaq_value as number,
    }))

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem' }}>
          KOSPI/KOSDAQ 거래대금 30일
        </div>
        {data.stale && <div style={{ color: 'var(--warn)', fontSize: '0.75rem', fontWeight: 700 }}>갱신 확인 필요</div>}
      </div>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: C.text2, fontSize: 11 }} width={40} tickFormatter={v => `${v}`} />
            <Tooltip
              contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
              labelStyle={{ color: C.text2 }}
              formatter={(v, name) => [`${fmtFixed(v as number, 2)}조`, name as string]}
            />
            <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
            <Bar dataKey="kospi" fill={C.accent} name="KOSPI" barSize={8} />
            <Bar dataKey="kosdaq" fill={C.info} name="KOSDAQ" barSize={8} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '56px 0', fontSize: '0.85rem' }}>
          데이터가 없습니다
        </div>
      )}
    </Card>
  )
}

export function Volume() {
  const [asset, setAsset] = useState<AssetTab>(() => readAssetTab(['coin', 'kr', 'us']))
  const { data, loading, error, refetch, lastUpdated } = useApi<VolumeData>(asset === 'coin' ? '/api/volume-data' : null, 300_000)
  const { data: weekly } = useApi<WeeklyData>(asset === 'coin' ? '/api/volume-weekly' : null, 3_600_000)
  const { data: dailyRsi } = useApi<RsiData>(asset === 'coin' ? '/api/btc-daily-rsi' : null, 3_600_000)
  const { data: weeklyRsi } = useApi<RsiData>(asset === 'coin' ? '/api/btc-weekly-rsi' : null, 3_600_000)
  const { data: fgHistory } = useApi<FearGreedHistory>(asset === 'coin' ? '/api/fear-greed-history' : null, 3_600_000)
  const stockFearGreedApi = useApi<StockFearGreedData>(asset === 'us' ? '/api/volume/stock-fear-greed' : null, 300_000)
  const putcallApi = useApi<PutcallData>(asset === 'us' ? '/api/volume/putcall?days=90' : null, 300_000)
  const krMarketVolumeApi = useApi<KrMarketVolumeData>(asset === 'kr' ? '/api/volume/kr-market-volume?days=30' : null, 300_000)

  function handleAssetChange(next: AssetTab) {
    setAsset(next)
    replaceAssetTab(next)
  }

  const tabs = <AssetTabs asset={asset} allowedTabs={['coin', 'kr', 'us']} onChange={handleAssetChange} />

  if (asset === 'us') {
    const usSections = resolveUsVolumeSections({
      stock: stockFearGreedApi,
      putcall: putcallApi,
    })
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        {usSections.stock === 'data' && (
          <>
            <LastUpdated timestamp={stockFearGreedApi.lastUpdated} failed={!!stockFearGreedApi.error} />
            <StockFearGreedView data={stockFearGreedApi.data as StockFearGreedData} />
          </>
        )}
        {usSections.stock === 'loading' && <Skeleton />}
        {usSections.stock === 'error' && <ErrorState error={stockFearGreedApi.error ?? ''} onRetry={stockFearGreedApi.refetch} />}
        {usSections.putcall === 'data' && <PutcallView data={putcallApi.data as PutcallData} />}
        {usSections.putcall === 'loading' && <Skeleton />}
        {usSections.putcall === 'error' && <ErrorState error={putcallApi.error ?? ''} onRetry={putcallApi.refetch} />}
      </div>
    )
  }

  if (asset === 'kr') {
    if (krMarketVolumeApi.error && !krMarketVolumeApi.data) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tabs}
          <ErrorState error={krMarketVolumeApi.error} onRetry={krMarketVolumeApi.refetch} />
        </div>
      )
    }
    if (krMarketVolumeApi.loading || !krMarketVolumeApi.data) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tabs}
          <Skeleton />
        </div>
      )
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <LastUpdated timestamp={krMarketVolumeApi.lastUpdated} failed={!!krMarketVolumeApi.error} />
        <KrMarketVolumeView data={krMarketVolumeApi.data} />
      </div>
    )
  }

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

  const { current, avg_30d, history } = data

  // 최근 30일 히스토리 차트용 (오래된 → 최신)
  const histChart = (history || []).slice(-30).map(r => ({
    date: r.date?.slice(5),
    upbit: r.upbit_krw ?? 0,
    bithumb: r.bithumb_krw ?? 0,
  }))

  // 주간 차트
  const weeklyChart = (weekly?.weeks || []).map(w => ({
    week: w.week?.replace(/\d{4}-W/, 'W'),
    upbit: w.upbit_krw,
    bithumb: w.bithumb_krw,
    total: w.total_krw,
  }))

  // RSI 차트
  const dailyRsiChart = (dailyRsi?.rsi || []).map(r => ({
    date: r.date?.slice(5),
    rsi: r.rsi,
  }))
  const weeklyRsiChart = (weeklyRsi?.rsi || []).map(r => ({
    date: r.date?.slice(5),
    rsi: r.rsi,
  }))

  // 공포탐욕 차트
  const fgChart = (fgHistory?.history || []).slice(-30).map(r => ({
    date: r.date?.slice(5),
    value: r.value,
  }))

  const latestDailyRsi = dailyRsi?.rsi?.at(-1)?.rsi ?? null
  const latestWeeklyRsi = weeklyRsi?.rsi?.at(-1)?.rsi ?? null

  // 30d 평균 대비 현재 비율
  const upbitVsAvg = avg_30d.upbit_krw && current.upbit_krw
    ? Number(((current.upbit_krw / avg_30d.upbit_krw - 1) * 100).toFixed(1))
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {tabs}
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      {/* 24시간 요약 목록 */}
      <Card>
        <div style={{ color: 'var(--text)', fontSize: 15, fontWeight: 600, marginBottom: 4 }}>24시간 요약</div>
        <div className="v2-list">
          <div className="v2-row" style={{ minHeight: 56 }}>
            <span className="v2-nowrap">업비트 24h 거래대금</span>
            <span>
              {upbitVsAvg != null && (
                <span className="v2-note v2-nowrap" style={{ color: changeColor(upbitVsAvg) }}>
                  30일 평균 대비 {changeArrow(upbitVsAvg)} {fmtSignedPct(upbitVsAvg, 1)}
                </span>
              )}
              <span style={{ color: 'var(--accent)' }}>{current.upbit_krw != null ? `${fmtFixed(current.upbit_krw, 2)}조` : '—'}</span>
            </span>
          </div>
          <div className="v2-row" style={{ minHeight: 56 }}>
            <span className="v2-nowrap">빗썸 24h 거래대금</span>
            <span>
              <span className="v2-note v2-nowrap" style={{ color: 'var(--text-2)' }}>
                30일 평균 {avg_30d.bithumb_krw ? `${fmtFixed(avg_30d.bithumb_krw, 2)}조` : '—'}
              </span>
              <span style={{ color: 'var(--neutral-series)' }}>{current.bithumb_krw != null ? `${fmtFixed(current.bithumb_krw, 2)}조` : '—'}</span>
            </span>
          </div>
          <div className="v2-row" style={{ minHeight: 56 }}>
            <span className="v2-nowrap">합산 거래대금</span>
            <span style={{ color: 'var(--text)' }}>{current.total_krw != null ? `${fmtFixed(current.total_krw, 2)}조` : '—'}</span>
          </div>
          <VolumeRatio upbit={current.upbit_krw} bithumb={current.bithumb_krw} />
          <div className="v2-row" style={{ minHeight: 56 }}>
            <span className="v2-nowrap">BTC 일봉 RSI</span>
            <span>
              {latestDailyRsi != null && (
                <span className="v2-note v2-nowrap" style={{ color: rsiState(latestDailyRsi).color }}>{rsiState(latestDailyRsi).label}</span>
              )}
              <span style={{ color: latestDailyRsi != null ? rsiState(latestDailyRsi).color : 'var(--text-3)' }}>
                {latestDailyRsi != null ? fmtFixed(latestDailyRsi, 1) : '—'}
              </span>
            </span>
          </div>
          <div className="v2-row">
            <span className="v2-nowrap">BTC 주봉 RSI</span>
            <span>
              {latestWeeklyRsi != null && (
                <span className="v2-note v2-nowrap" style={{ color: rsiState(latestWeeklyRsi).color }}>{rsiState(latestWeeklyRsi).label}</span>
              )}
              <span style={{ color: latestWeeklyRsi != null ? rsiState(latestWeeklyRsi).color : 'var(--text-3)' }}>
                {latestWeeklyRsi != null ? fmtFixed(latestWeeklyRsi, 1) : '—'}
              </span>
            </span>
          </div>
        </div>
      </Card>

      {/* 일별 거래대금 — 가로 막대 */}
      {histChart.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
            일별 거래대금 (최근 {histChart.length}일, 단위: 조원)
          </div>
          <ResponsiveContainer width="100%" height={Math.max(160, histChart.length * 22)}>
            <BarChart data={histChart} layout="vertical" barSize={14} margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
              <XAxis type="number" tick={{ fill: C.text3, fontSize: 11 }} tickFormatter={(v) => fmtFixed(v as number, 1)} />
              <YAxis type="category" dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} width={46} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                labelStyle={{ color: C.text2 }}
                formatter={(v) => [`${fmtFixed(v as number, 2)}조`, '']}
              />
              <Bar dataKey="bithumb" stackId="a" fill={C.neutralSeries} name="빗썸" />
              <Bar dataKey="upbit" stackId="a" fill={C.accent} name="업비트" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* 주간 거래대금 — 가로 막대 */}
      {weeklyChart.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>주간 거래대금 (최근 12주)</div>
          <ResponsiveContainer width="100%" height={Math.max(160, weeklyChart.length * 28)}>
            <BarChart data={weeklyChart} layout="vertical" barSize={16} margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
              <XAxis type="number" tick={{ fill: C.text3, fontSize: 11 }} tickFormatter={(v) => fmtFixed(v as number, 1)} />
              <YAxis type="category" dataKey="week" tick={{ fill: C.text3, fontSize: 11 }} width={46} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                formatter={(v) => [`${fmtFixed(v as number, 2)}조`, '']}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
              <Bar dataKey="bithumb" stackId="a" fill={C.neutralSeries} name="빗썸" />
              <Bar dataKey="upbit" stackId="a" fill={C.accent} name="업비트" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* RSI 차트 2개 */}
      <div className="grid-2" style={{ gap: 12 }}>
        {dailyRsiChart.length > 0 && (
          <Card>
            <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>BTC 일봉 RSI</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={dailyRsiChart}>
                <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} tick={{ fill: C.text3, fontSize: 11 }} width={34} />
                <Tooltip
                  contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                  labelStyle={{ color: C.text2 }}
                />
                <ReferenceLine y={70} stroke={C.warn} strokeDasharray="3 3" />
                <ReferenceLine y={30} stroke={C.ok} strokeDasharray="3 3" />
                <Line type="monotone" dataKey="rsi" stroke={C.violet} dot={false} strokeWidth={2} name="RSI" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        )}

        {weeklyRsiChart.length > 0 && (
          <Card>
            <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>BTC 주봉 RSI</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={weeklyRsiChart}>
                <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} tick={{ fill: C.text3, fontSize: 11 }} width={34} />
                <Tooltip
                  contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                  labelStyle={{ color: C.text2 }}
                />
                <ReferenceLine y={70} stroke={C.warn} strokeDasharray="3 3" />
                <ReferenceLine y={30} stroke={C.ok} strokeDasharray="3 3" />
                <Line type="monotone" dataKey="rsi" stroke={C.info} dot={false} strokeWidth={2} name="주봉 RSI" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        )}
      </div>

      {/* 공포탐욕 30일 추이 */}
      {fgChart.length > 0 && (
        <Card>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>공포탐욕 지수 추이 (30일)</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={fgChart}>
              <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fill: C.text3, fontSize: 11 }} width={34} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                labelStyle={{ color: C.text2 }}
              />
              <ReferenceLine y={75} stroke={C.warn} strokeDasharray="3 3" label={{ value: '탐욕', fill: C.warn, fontSize: 11 }} />
              <ReferenceLine y={25} stroke={C.ok} strokeDasharray="3 3" label={{ value: '공포', fill: C.ok, fontSize: 11 }} />
              <Line type="monotone" dataKey="value" stroke={C.accent} dot={false} strokeWidth={2} name="공포탐욕" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

    </div>
  )
}
