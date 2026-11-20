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
import { C, softBg } from '../../lib/theme'
import { buildCvdChart, type CvdChartPoint, type CvdPoint } from './cvdChartData'

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

interface CvdDetail {
  symbol: string
  timeframe: string
  chart: CvdPoint[]
  score: ScreenerResult
}

const GRADE_COLOR: Record<string, string> = {
  S: C.accent,
  A: C.ok,
  B: C.text,
  C: C.text2,
  D: C.text3,
}

const GRADE_BG: Record<string, string> = {
  S: softBg(C.accent, 0.2),
  A: softBg(C.ok, 0.12),
  B: C.segActive,
  C: C.surface2,
  D: C.surface2,
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

// 스퀴즈 점 — 범례와 목록 행이 같이 쓴다
function SqueezeDot({ color, label }: { color: string; label?: string }) {
  return (
    <span
      aria-label={label}
      style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, verticalAlign: 'baseline' }}
    />
  )
}

function FactorBar({ label, score, factorKey }: { label: string; score: number; factorKey?: string }) {
  const color = score >= 70 ? 'var(--ok)' : score >= 50 ? 'var(--accent)' : score >= 30 ? 'var(--warn)' : 'var(--neutral-series)'
  const showSqueezeBadge = factorKey === 'bb_squeeze' && score >= 70
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ color: 'var(--text-2)', fontSize: '0.75rem' }}>
          {label}
          {showSqueezeBadge && (
            <span style={{
              marginLeft: 6, padding: '1px 6px', borderRadius: 4, fontSize: '0.75rem',
              background: softBg(C.warn, 0.2), color: 'var(--warn)', fontWeight: 700,
            }}>
              스퀴즈!
            </span>
          )}
        </span>
        <span style={{ color, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 600 }}>{score.toFixed(0)}</span>
      </div>
      <div style={{ height: 4, background: 'var(--seg-active)', borderRadius: 2 }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: 2, transition: 'width 0.4s' }} />
      </div>
    </div>
  )
}

export function Alt() {
  const [timeframe, setTimeframe] = useState<Timeframe>('4h')
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const { data: screener, error, refetch, lastUpdated } = useApi<ScreenerData>(
    `/api/cvd-screener?timeframe=${timeframe}`,
    300_000,
    // 타임프레임 변경 시 재조회
  )

  const { data: detail } = useApi<CvdDetail>(
    selectedSymbol ? `/api/cvd?symbol=${encodeURIComponent(selectedSymbol)}&timeframe=${timeframe}` : null,
    300_000,
  )

  // 타임프레임 선택 — 뼈대·오류 화면에서도 보여 실패한 주기에서 빠져나올 수 있게 한다
  const timeframeBar = (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <span style={{ color: 'var(--text-3)', fontSize: '0.8rem' }}>주기</span>
      <div className="v2-seg" role="group" aria-label="주기">
        {(['1h', '4h', '1d'] as Timeframe[]).map(tf => (
          <button
            key={tf}
            type="button"
            className="v2-seg-btn"
            aria-pressed={timeframe === tf}
            onClick={() => setTimeframe(tf)}
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {tf}
          </button>
        ))}
      </div>
      {screener && (
        <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: '0.75rem' }}>
          {screener.total}개 종목 분석
        </span>
      )}
    </div>
  )

  if (!screener) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {timeframeBar}
        {error ? <ErrorState error={error} onRetry={refetch} /> : <Skeleton />}
      </div>
    )
  }

  // CVD 차트 (선택 종목) + delta 계산
  const cvdChart: CvdChartPoint[] = buildCvdChart(detail?.chart ?? [])

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
          divergenceZones.push({ start: streakStart, end: cvdChart[i - 1].xKey, type: streakType })
        }
        streak = currentType ? 1 : 0
        streakType = currentType
        streakStart = cvdChart[i].xKey
      }
    }
    // 마지막 구간 처리
    if (streak >= 3 && streakType) {
      divergenceZones.push({ start: streakStart, end: cvdChart[cvdChart.length - 1].xKey, type: streakType })
    }
  }

  const formatCvdAxisLabel = (value: unknown) => {
    const index = Number.parseInt(String(value).split(':', 1)[0], 10)
    return Number.isNaN(index) ? String(value) : (cvdChart[index]?.dateLabel ?? String(value))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      {timeframeBar}

      {/* 스크리너 테이블 */}
      <Card>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 10 }}>
          CVD 11팩터 스크리너 — {timeframe} 기준
        </div>
        {/* 범례: 등급 기준(cvd_service GRADE_THRESHOLDS)과 점의 뜻(bb_squeeze 70+/50+) */}
        <div style={{ color: 'var(--text-2)', fontSize: 12, lineHeight: 1.6, marginBottom: 10 }}>
          <div>등급: S 80+ · A 65+ · B 50+ · C 35+ · D 35 미만</div>
          <div>
            <SqueezeDot color="var(--warn)" /> 볼린저밴드 스퀴즈 감지 · <SqueezeDot color="var(--neutral-series)" /> 보통
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {screener.results.map((r, i) => (
            <button
              key={r.symbol}
              type="button"
              className="cvd-row"
              aria-pressed={selectedSymbol === r.symbol}
              onClick={() => setSelectedSymbol(r.symbol === selectedSymbol ? null : r.symbol)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                color: 'inherit', font: 'inherit', textAlign: 'left', width: '100%',
                background: selectedSymbol === r.symbol ? 'var(--surface-2)' : 'transparent',
                border: `1px solid ${selectedSymbol === r.symbol ? 'var(--border-strong)' : 'transparent'}`,
                transition: 'background 0.15s',
              }}
            >
              {/* 순위 */}
              <span style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', width: 20, textAlign: 'right' }}>
                {i + 1}
              </span>

              {/* 종목 */}
              <span style={{ color: 'var(--text)', fontSize: '0.85rem', fontWeight: 600, width: 90 }}>
                {r.symbol.replace('/USDT', '')}
              </span>

              {/* 등급 배지 */}
              <span style={{
                padding: '2px 10px', borderRadius: 8, fontSize: '0.8rem', fontWeight: 700,
                background: GRADE_BG[r.grade] ?? GRADE_BG.C,
                color: GRADE_COLOR[r.grade] ?? C.text2,
                width: 36, textAlign: 'center',
              }}>
                {r.grade}
              </span>

              {/* BB 스퀴즈 아이콘 */}
              <span style={{ width: 16, textAlign: 'center' }}>
                {r.factors?.bb_squeeze >= 70 ? (
                  <SqueezeDot color="var(--warn)" label="볼린저밴드 스퀴즈 감지" />
                ) : r.factors?.bb_squeeze >= 50 ? (
                  <SqueezeDot color="var(--neutral-series)" label="볼린저밴드 보통" />
                ) : null}
              </span>

              {/* 점수 바 */}
              <div style={{ flex: 1, height: 6, background: 'var(--seg-active)', borderRadius: 3 }}>
                <div style={{
                  height: '100%',
                  width: `${r.score}%`,
                  background: GRADE_COLOR[r.grade] ?? C.text2,
                  borderRadius: 3, transition: 'width 0.4s',
                }} />
              </div>

              <span style={{ color: GRADE_COLOR[r.grade] ?? C.text2, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 700, width: 36, textAlign: 'right' }}>
                {r.score.toFixed(0)}
              </span>
            </button>
          ))}
        </div>
      </Card>

      {/* 선택 종목 상세 */}
      {selectedSymbol && detail && (
        <>
          {/* CVD 차트 */}
          {cvdChart.length > 0 && (
            <Card>
              <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
                {selectedSymbol} CVD vs 가격 ({timeframe})
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={cvdChart}>
                  <XAxis dataKey="xKey" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" tickFormatter={formatCvdAxisLabel} />
                  <YAxis yAxisId="cvd" orientation="left" tick={{ fill: C.info, fontSize: 11 }} width={45} />
                  <YAxis yAxisId="price" orientation="right" domain={['auto', 'auto']} tick={{ fill: C.accent, fontSize: 11 }} width={50} />
                  <Tooltip
                    contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                    labelStyle={{ color: C.text2 }}
                    labelFormatter={formatCvdAxisLabel}
                  />
                  <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
                  {divergenceZones.map((zone, idx) => (
                    <ReferenceArea
                      key={idx}
                      yAxisId="cvd"
                      x1={zone.start}
                      x2={zone.end}
                      fill={zone.type === 'bearish' ? softBg(C.down, 0.12) : softBg(C.up, 0.12)}
                      stroke="none"
                    />
                  ))}
                  <Line yAxisId="cvd" type="monotone" dataKey="cvd" stroke={C.info} dot={false} strokeWidth={2} name="CVD" />
                  <Line yAxisId="price" type="monotone" dataKey="close" stroke={C.accent} dot={false} strokeWidth={2} name="가격" />
                </ComposedChart>
              </ResponsiveContainer>
              {/* CVD Delta (매수/매도 전환) */}
              <div style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: 8, marginBottom: 4 }}>
                CVD Delta (봉간 변화량)
              </div>
              <ResponsiveContainer width="100%" height={80}>
                <ComposedChart data={cvdChart}>
                  <XAxis dataKey="xKey" tick={false} axisLine={false} />
                  <YAxis tick={{ fill: C.text3, fontSize: 11 }} width={45} />
                  <Tooltip
                    contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                    labelStyle={{ color: C.text2 }}
                    labelFormatter={formatCvdAxisLabel}
                  />
                  <Bar dataKey="delta" name="CVD Delta">
                    {cvdChart.map((entry, idx) => (
                      <Cell key={idx} fill={entry.delta >= 0 ? C.up : C.down} />
                    ))}
                  </Bar>
                </ComposedChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* 11팩터 스코어 상세 */}
          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ color: 'var(--text-2)', fontSize: '0.75rem' }}>
                {selectedSymbol} — 팩터 분석
              </div>
              <div style={{
                padding: '4px 14px', borderRadius: 8,
                background: GRADE_BG[detail.score.grade] ?? GRADE_BG.C,
                color: GRADE_COLOR[detail.score.grade] ?? C.text2,
                fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1rem',
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
