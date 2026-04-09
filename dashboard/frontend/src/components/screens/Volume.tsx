import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, Legend,
} from 'recharts'

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

export function Volume() {
  const { data, loading, error } = useApi<VolumeData>('/api/volume-data', 300_000)
  const { data: weekly } = useApi<WeeklyData>('/api/volume-weekly', 3_600_000)
  const { data: dailyRsi } = useApi<RsiData>('/api/btc-daily-rsi', 3_600_000)
  const { data: weeklyRsi } = useApi<RsiData>('/api/btc-weekly-rsi', 3_600_000)
  const { data: fgHistory } = useApi<FearGreedHistory>('/api/fear-greed-history', 3_600_000)

  if (error) return <div style={{ color: '#f87171', padding: 16 }}>데이터 로드 실패: {error}</div>
  if (loading || !data) {
    return <div style={{ color: '#64748b', padding: 32, textAlign: 'center' }}>볼륨 데이터 로드 중...</div>
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

      {/* 상단 요약 카드 4개 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
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

      {/* 60일 일별 거래대금 바 차트 */}
      {histChart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
            일별 거래대금 (최근 {histChart.length}일, 단위: 조원)
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={histChart} barSize={6}>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={35} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v) => [`${(v as number).toFixed(2)}조`, '']}
              />
              <Bar dataKey="upbit" stackId="a" fill="#f97316" name="업비트" />
              <Bar dataKey="bithumb" stackId="a" fill="#60a5fa" name="빗썸" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* 주간 거래량 차트 */}
      {weeklyChart.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>주간 거래대금 (최근 12주)</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={weeklyChart} barSize={14}>
              <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={35} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                formatter={(v) => [`${(v as number).toFixed(2)}조`, '']}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
              <Bar dataKey="upbit" stackId="a" fill="#f97316" name="업비트" />
              <Bar dataKey="bithumb" stackId="a" fill="#60a5fa" name="빗썸" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* RSI 차트 2개 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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
