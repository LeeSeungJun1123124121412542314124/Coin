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

function VolumeRatio({ upbit, bithumb }: { upbit: number | null; bithumb: number | null }) {
  const total = (upbit ?? 0) + (bithumb ?? 0)
  if (total === 0) return null
  const upbitPct = ((upbit ?? 0) / total * 100).toFixed(1)
  const bithumbPct = ((bithumb ?? 0) / total * 100).toFixed(1)
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 4 }}>
        <div style={{ width: `${upbitPct}%`, background: '#f97316' }} />
        <div style={{ width: `${bithumbPct}%`, background: '#60a5fa' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#64748b' }}>
        <span style={{ color: '#f97316' }}>업비트 {upbitPct}%</span>
        <span style={{ color: '#60a5fa' }}>빗썸 {bithumbPct}%</span>
      </div>
    </div>
  )
}

function RsiGauge({ value }: { value: number }) {
  const color = value >= 70 ? '#f87171' : value <= 30 ? '#4ade80' : '#94a3b8'
  const label = value >= 70 ? '과매수' : value <= 30 ? '과매도' : '중립'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ fontSize: '2rem', fontWeight: 700, color }}>{value.toFixed(1)}</div>
      <div>
        <div style={{ color, fontSize: '0.8rem', fontWeight: 600 }}>{label}</div>
        <div style={{ color: '#64748b', fontSize: '0.75rem' }}>RSI</div>
      </div>
    </div>
  )
}

function StockFearGreedView({ data }: { data: StockFearGreedData }) {
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 4 }}>CNN Fear & Greed</div>
          <div style={{ color: '#64748b', fontSize: '0.72rem' }}>
            {data.updated_at ? new Date(data.updated_at).toLocaleString('ko-KR') : '데이터 없음'}
            {data.stale && <span style={{ color: '#f59e0b', marginLeft: 8 }}>갱신 확인 필요</span>}
          </div>
        </div>
        <div style={{ color: '#e2e8f0', fontSize: '0.92rem', fontWeight: 700 }}>
          {data.rating ?? '-'}
        </div>
      </div>
      {data.value != null ? (
        <GaugeChart value={Math.round(data.value)} label="Stock F&G" size={180} />
      ) : (
        <div style={{ color: '#64748b', textAlign: 'center', padding: '56px 0', fontSize: '0.85rem' }}>
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
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 4 }}>CBOE Put/Call</div>
          <div style={{ color: '#64748b', fontSize: '0.72rem' }}>
            {latest?.date ?? '데이터 없음'}
            {data.stale && <span style={{ color: '#f59e0b', marginLeft: 8 }}>갱신 확인 필요</span>}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ color: signal.color, fontSize: '1.35rem', fontWeight: 800 }}>
            {equity != null ? equity.toFixed(2) : '-'}
          </div>
          <div style={{ color: signal.color, fontSize: '0.75rem', fontWeight: 700 }}>
            {signal.label} · {signal.help}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {(['equity', 'total', 'index'] as PutcallSeries[]).map(item => (
          <button
            key={item}
            type="button"
            onClick={() => setSeries(item)}
            style={{
              border: '1px solid #334155',
              background: series === item ? '#334155' : '#0f172a',
              color: series === item ? '#e2e8f0' : '#94a3b8',
              borderRadius: 6,
              padding: '6px 10px',
              fontSize: '0.75rem',
              fontWeight: 700,
            }}
          >
            {seriesLabel[item]}
          </button>
        ))}
      </div>

      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={190}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} width={34} domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(v) => [typeof v === 'number' ? v.toFixed(2) : v, seriesLabel[series]]}
            />
            <ReferenceLine y={0.7} stroke="#f87171" strokeDasharray="3 3" />
            <ReferenceLine y={1.0} stroke="#4ade80" strokeDasharray="3 3" />
            <Line type="monotone" dataKey={series} stroke="#38bdf8" dot={false} strokeWidth={2} name={seriesLabel[series]} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ color: '#64748b', textAlign: 'center', padding: '48px 0', fontSize: '0.85rem' }}>
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
        <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
          KOSPI/KOSDAQ 거래대금 30일
        </div>
        {data.stale && <div style={{ color: '#f59e0b', fontSize: '0.75rem', fontWeight: 700 }}>갱신 확인 필요</div>}
      </div>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} width={40} tickFormatter={v => `${v}`} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(v, name) => [`${(v as number).toFixed(2)}조`, name as string]}
            />
            <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
            <Bar dataKey="kospi" fill="#38bdf8" name="KOSPI" barSize={8} />
            <Bar dataKey="kosdaq" fill="#f59e0b" name="KOSDAQ" barSize={8} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ color: '#64748b', textAlign: 'center', padding: '56px 0', fontSize: '0.85rem' }}>
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
            <LastUpdated timestamp={stockFearGreedApi.lastUpdated} />
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
        <LastUpdated timestamp={krMarketVolumeApi.lastUpdated} />
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
    ? ((current.upbit_krw / avg_30d.upbit_krw - 1) * 100).toFixed(1)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {tabs}
      <LastUpdated timestamp={lastUpdated} />
      {/* 상단 요약 카드 4개 */}
      <div className="grid-4" style={{ gap: 12 }}>
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>업비트 24h 거래대금</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f97316' }}>
            {current.upbit_krw != null ? `${current.upbit_krw.toFixed(2)}조` : '—'}
          </div>
          {upbitVsAvg && (
            <div style={{ color: +upbitVsAvg > 0 ? '#4ade80' : '#f87171', fontSize: '0.75rem', marginTop: 4 }}>
              30일 평균 대비 {+upbitVsAvg > 0 ? '+' : ''}{upbitVsAvg}%
            </div>
          )}
        </Card>

        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>빗썸 24h 거래대금</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#60a5fa' }}>
            {current.bithumb_krw != null ? `${current.bithumb_krw.toFixed(2)}조` : '—'}
          </div>
          <div style={{ color: '#64748b', fontSize: '0.75rem', marginTop: 4 }}>
            30일 평균 {avg_30d.bithumb_krw ? `${avg_30d.bithumb_krw.toFixed(2)}조` : '—'}
          </div>
        </Card>

        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>합산 거래대금</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#e2e8f0' }}>
            {current.total_krw != null ? `${current.total_krw.toFixed(2)}조` : '—'}
          </div>
          <VolumeRatio upbit={current.upbit_krw} bithumb={current.bithumb_krw} />
        </Card>

        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 8 }}>BTC 일봉 RSI</div>
          {latestDailyRsi != null ? (
            <RsiGauge value={latestDailyRsi} />
          ) : (
            <div style={{ color: '#64748b', fontSize: '0.85rem' }}>데이터 없음</div>
          )}
          {latestWeeklyRsi != null && (
            <div style={{ marginTop: 8, color: '#64748b', fontSize: '0.75rem' }}>
              주봉 RSI {latestWeeklyRsi.toFixed(1)}
            </div>
          )}
        </Card>
      </div>

      {/* 일별 거래대금 — 가로 막대 */}
      {histChart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
            일별 거래대금 (최근 {histChart.length}일, 단위: 조원)
          </div>
          <ResponsiveContainer width="100%" height={Math.max(160, histChart.length * 22)}>
            <BarChart data={histChart} layout="vertical" barSize={14} margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
              <XAxis type="number" tick={{ fill: '#64748b', fontSize: 9 }} tickFormatter={(v) => `${(v as number).toFixed(1)}`} />
              <YAxis type="category" dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} width={42} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v) => [`${(v as number).toFixed(2)}조`, '']}
              />
              <Bar dataKey="bithumb" stackId="a" fill="#60a5fa" name="빗썸" />
              <Bar dataKey="upbit" stackId="a" fill="#f97316" name="업비트" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* 주간 거래대금 — 가로 막대 */}
      {weeklyChart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>주간 거래대금 (최근 12주)</div>
          <ResponsiveContainer width="100%" height={Math.max(160, weeklyChart.length * 28)}>
            <BarChart data={weeklyChart} layout="vertical" barSize={16} margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
              <XAxis type="number" tick={{ fill: '#64748b', fontSize: 9 }} tickFormatter={(v) => `${(v as number).toFixed(1)}`} />
              <YAxis type="category" dataKey="week" tick={{ fill: '#64748b', fontSize: 10 }} width={42} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                formatter={(v) => [`${(v as number).toFixed(2)}조`, '']}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
              <Bar dataKey="bithumb" stackId="a" fill="#60a5fa" name="빗썸" />
              <Bar dataKey="upbit" stackId="a" fill="#f97316" name="업비트" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* RSI 차트 2개 */}
      <div className="grid-2" style={{ gap: 12 }}>
        {dailyRsiChart.length > 0 && (
          <Card>
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>BTC 일봉 RSI</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={dailyRsiChart}>
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} width={30} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#94a3b8' }}
                />
                <ReferenceLine y={70} stroke="#f87171" strokeDasharray="3 3" />
                <ReferenceLine y={30} stroke="#4ade80" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="rsi" stroke="#a78bfa" dot={false} strokeWidth={2} name="RSI" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        )}

        {weeklyRsiChart.length > 0 && (
          <Card>
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>BTC 주봉 RSI</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={weeklyRsiChart}>
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} width={30} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#94a3b8' }}
                />
                <ReferenceLine y={70} stroke="#f87171" strokeDasharray="3 3" />
                <ReferenceLine y={30} stroke="#4ade80" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="rsi" stroke="#f59e0b" dot={false} strokeWidth={2} name="주봉 RSI" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        )}
      </div>

      {/* 공포탐욕 30일 추이 */}
      {fgChart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>공포탐욕 지수 추이 (30일)</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={fgChart}>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} width={30} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <ReferenceLine y={75} stroke="#f87171" strokeDasharray="3 3" label={{ value: '탐욕', fill: '#f87171', fontSize: 10 }} />
              <ReferenceLine y={25} stroke="#4ade80" strokeDasharray="3 3" label={{ value: '공포', fill: '#4ade80', fontSize: 10 }} />
              <Line type="monotone" dataKey="value" stroke="#60a5fa" dot={false} strokeWidth={2} name="공포탐욕" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

    </div>
  )
}
