import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import {
  Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, ComposedChart, Bar, Cell, ReferenceArea,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'

interface ScreenerResult {
  symbol: string
  score: number
  grade: string
  factors: Record<string, number>
  error?: string
}

interface ScreenerData {
  timeframe: string
  results: ScreenerResult[]
  total: number
}

interface CvdPoint {
  date: string
  cvd: number
  close: number | null
}

interface CvdChartPoint extends CvdPoint {
  delta: number
}

interface CvdDetail {
  symbol: string
  timeframe: string
  chart: CvdPoint[]
  score: ScreenerResult
}

const GRADE_COLOR: Record<string, string> = {
  S: '#f59e0b',
  A: '#4ade80',
  B: '#60a5fa',
  C: '#94a3b8',
  D: '#f87171',
}

const GRADE_BG: Record<string, string> = {
  S: 'rgba(245,158,11,0.15)',
  A: 'rgba(74,222,128,0.12)',
  B: 'rgba(96,165,250,0.12)',
  C: 'rgba(148,163,184,0.10)',
  D: 'rgba(248,113,113,0.10)',
}

const FACTOR_LABELS: Record<string, string> = {
  cvd_divergence: 'CVD 다이버전스',
  cvd_slope: 'CVD 기울기',
  rsi: 'RSI',
  bb_pct_b: 'BB %B',
  bb_squeeze: 'BB 스퀴즈',
  oi_change: 'OI 변화',
  funding_rate: '펀딩비',
  volume_strength: '거래량 강도',
  close_position: '종가 위치',
  atr: 'ATR 변동성',
  ema_trend: 'EMA 추세',
}

type Timeframe = '1h' | '4h' | '1d'

function FactorBar({ label, score, factorKey }: { label: string; score: number; factorKey?: string }) {
  const color = score >= 70 ? '#4ade80' : score >= 50 ? '#60a5fa' : score >= 30 ? '#f59e0b' : '#f87171'
  const showSqueezeBadge = factorKey === 'bb_squeeze' && score >= 70
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ color: '#94a3b8', fontSize: '0.72rem' }}>
          {label}
          {showSqueezeBadge && (
            <span style={{
              marginLeft: 6, padding: '1px 6px', borderRadius: 4, fontSize: '0.65rem',
              background: 'rgba(245,158,11,0.2)', color: '#f59e0b', fontWeight: 700,
            }}>
              스퀴즈!
            </span>
          )}
        </span>
        <span style={{ color, fontSize: '0.72rem', fontWeight: 600 }}>{score.toFixed(0)}</span>
      </div>
      <div style={{ height: 4, background: '#334155', borderRadius: 2 }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: 2, transition: 'width 0.4s' }} />
      </div>
    </div>
  )
}

export function Alt() {
  const [timeframe, setTimeframe] = useState<Timeframe>('4h')
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const { data: screener, loading, error, refetch, lastUpdated } = useApi<ScreenerData>(
    `/api/cvd-screener?timeframe=${timeframe}`,
    300_000,
    // 타임프레임 변경 시 재조회
  )

  const { data: detail } = useApi<CvdDetail>(
    selectedSymbol ? `/api/cvd?symbol=${encodeURIComponent(selectedSymbol)}&timeframe=${timeframe}` : null,
    300_000,
  )

  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (loading || !screener) return <Skeleton />

  // CVD 차트 (선택 종목) + delta 계산
  const cvdChart: CvdChartPoint[] = (detail?.chart ?? []).slice(-60).map((p, i, arr) => ({
    date: p.date?.slice(5),
    cvd: p.cvd,
    close: p.close ?? null,
    delta: i > 0 ? p.cvd - arr[i - 1].cvd : 0,
  }))

  // 다이버전스 구간 감지
  const divergenceZones: { start: string; end: string; type: 'bearish' | 'bullish' }[] = []
  if (cvdChart.length >= 3) {
    let streak = 0
    let streakType: 'bearish' | 'bullish' | null = null
    let streakStart = ''

    for (let i = 1; i < cvdChart.length; i++) {
      const priceDelta = (cvdChart[i].close ?? 0) - (cvdChart[i - 1].close ?? 0)
      const cvdDelta = cvdChart[i].cvd - cvdChart[i - 1].cvd
      let currentType: 'bearish' | 'bullish' | null = null

      if (priceDelta > 0 && cvdDelta < 0) currentType = 'bearish'   // 가격↑ CVD↓
      else if (priceDelta < 0 && cvdDelta > 0) currentType = 'bullish' // 가격↓ CVD↑

      if (currentType && currentType === streakType) {
        streak++
      } else {
        if (streak >= 3 && streakType) {
          divergenceZones.push({ start: streakStart, end: cvdChart[i - 1].date, type: streakType })
        }
        streak = currentType ? 1 : 0
        streakType = currentType
        streakStart = cvdChart[i].date
      }
    }
    // 마지막 구간 처리
    if (streak >= 3 && streakType) {
      divergenceZones.push({ start: streakStart, end: cvdChart[cvdChart.length - 1].date, type: streakType })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} />
      {/* 타임프레임 선택 */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ color: '#64748b', fontSize: '0.8rem' }}>주기:</span>
        {(['1h', '4h', '1d'] as Timeframe[]).map(tf => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf)}
            style={{
              padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
              fontSize: '0.8rem',
              background: timeframe === tf ? '#2563eb' : '#1e293b',
              color: timeframe === tf ? '#fff' : '#94a3b8',
            }}
          >
            {tf}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: '0.75rem' }}>
          {screener.total}개 종목 분석
        </span>
      </div>

      {/* 스크리너 테이블 */}
      <Card>
        <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>
          CVD 11팩터 스크리너 — {timeframe} 기준
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {screener.results.map((r, i) => (
            <div
              key={r.symbol}
              onClick={() => setSelectedSymbol(r.symbol === selectedSymbol ? null : r.symbol)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                background: selectedSymbol === r.symbol ? '#1e293b' : 'transparent',
                border: `1px solid ${selectedSymbol === r.symbol ? '#334155' : 'transparent'}`,
                transition: 'background 0.15s',
              }}
            >
              {/* 순위 */}
              <span style={{ color: '#64748b', fontSize: '0.75rem', width: 20, textAlign: 'right' }}>
                {i + 1}
              </span>

              {/* 종목 */}
              <span style={{ color: '#e2e8f0', fontSize: '0.85rem', fontWeight: 600, width: 90 }}>
                {r.symbol.replace('/USDT', '')}
              </span>

              {/* 등급 배지 */}
              <span style={{
                padding: '2px 10px', borderRadius: 8, fontSize: '0.8rem', fontWeight: 700,
                background: GRADE_BG[r.grade] ?? GRADE_BG.C,
                color: GRADE_COLOR[r.grade] ?? '#94a3b8',
                width: 36, textAlign: 'center',
              }}>
                {r.grade}
              </span>

              {/* BB 스퀴즈 아이콘 */}
              <span style={{ width: 16, textAlign: 'center' }}>
                {r.factors?.bb_squeeze >= 70 ? (
                  <span style={{
                    display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                    background: '#f59e0b',
                  }} title="BB 스퀴즈 감지" />
                ) : r.factors?.bb_squeeze >= 50 ? (
                  <span style={{
                    display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                    background: '#475569',
                  }} title="BB 보통" />
                ) : null}
              </span>

              {/* 점수 바 */}
              <div style={{ flex: 1, height: 6, background: '#334155', borderRadius: 3 }}>
                <div style={{
                  height: '100%',
                  width: `${r.score}%`,
                  background: GRADE_COLOR[r.grade] ?? '#94a3b8',
                  borderRadius: 3, transition: 'width 0.4s',
                }} />
              </div>

              <span style={{ color: GRADE_COLOR[r.grade] ?? '#94a3b8', fontSize: '0.85rem', fontWeight: 700, width: 36, textAlign: 'right' }}>
                {r.score.toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {/* 선택 종목 상세 */}
      {selectedSymbol && detail && (
        <>
          {/* CVD 차트 */}
          {cvdChart.length > 0 && (
            <Card>
              <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
                {selectedSymbol} CVD vs 가격 ({timeframe})
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={cvdChart}>
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
                  <YAxis yAxisId="cvd" orientation="left" tick={{ fill: '#60a5fa', fontSize: 10 }} width={45} />
                  <YAxis yAxisId="price" orientation="right" domain={['auto', 'auto']} tick={{ fill: '#f59e0b', fontSize: 10 }} width={50} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    labelStyle={{ color: '#94a3b8' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
                  {divergenceZones.map((zone, idx) => (
                    <ReferenceArea
                      key={idx}
                      yAxisId="cvd"
                      x1={zone.start}
                      x2={zone.end}
                      fill={zone.type === 'bearish' ? 'rgba(248,113,113,0.08)' : 'rgba(74,222,128,0.08)'}
                      stroke="none"
                    />
                  ))}
                  <Line yAxisId="cvd" type="monotone" dataKey="cvd" stroke="#60a5fa" dot={false} strokeWidth={2} name="CVD" />
                  <Line yAxisId="price" type="monotone" dataKey="close" stroke="#f59e0b" dot={false} strokeWidth={2} name="가격" />
                </ComposedChart>
              </ResponsiveContainer>
              {/* CVD Delta (매수/매도 전환) */}
              <div style={{ color: '#64748b', fontSize: '0.7rem', marginTop: 8, marginBottom: 4 }}>
                CVD Delta (봉간 변화량)
              </div>
              <ResponsiveContainer width="100%" height={80}>
                <ComposedChart data={cvdChart}>
                  <XAxis dataKey="date" tick={false} axisLine={false} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 9 }} width={45} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    labelStyle={{ color: '#94a3b8' }}
                  />
                  <Bar dataKey="delta" name="CVD Delta">
                    {cvdChart.map((entry, idx) => (
                      <Cell key={idx} fill={entry.delta >= 0 ? '#4ade80' : '#f87171'} />
                    ))}
                  </Bar>
                </ComposedChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* 11팩터 스코어 상세 */}
          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
                {selectedSymbol} — 팩터 분석
              </div>
              <div style={{
                padding: '4px 14px', borderRadius: 8,
                background: GRADE_BG[detail.score.grade] ?? GRADE_BG.C,
                color: GRADE_COLOR[detail.score.grade] ?? '#94a3b8',
                fontWeight: 700, fontSize: '1rem',
              }}>
                {detail.score.grade} {detail.score.score.toFixed(0)}점
              </div>
            </div>
            <div className="grid-2" style={{ gap: '4px 24px' }}>
              {Object.entries(detail.score.factors).map(([key, val]) => (
                <FactorBar key={key} label={FACTOR_LABELS[key] ?? key} score={val} factorKey={key} />
              ))}
            </div>
          </Card>
        </>
      )}

    </div>
  )
}
