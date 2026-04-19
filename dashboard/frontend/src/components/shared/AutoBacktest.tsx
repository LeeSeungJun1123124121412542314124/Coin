import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import { apiFetch } from '../../lib/api'

// ────────────────────────────────────────
// 타입 정의
// ────────────────────────────────────────

interface IndicatorStat {
  name: string
  signal_count: number
  long_signals: number
  short_signals: number
  hit_count: number
  hit_rate: number        // 0-100
  avg_return_pct: number
  max_win_pct: number
  max_loss_pct: number
}

interface BacktestResult {
  symbol: string
  horizon_h: number
  lookback_bars: number
  computed_at: string
  from_cache: boolean
  indicators: IndicatorStat[]
}

// ────────────────────────────────────────
// 유틸: 적중률 색상
// ────────────────────────────────────────

function hitRateColor(rate: number): string {
  if (rate >= 60) return '#4ade80'
  if (rate >= 40) return '#fbbf24'
  return '#f87171'
}

// ────────────────────────────────────────
// 커스텀 Tooltip
// ────────────────────────────────────────

interface TooltipPayloadItem {
  payload: IndicatorStat
}

function BacktestTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: TooltipPayloadItem[]
}) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: '#0f172a',
      border: '1px solid #334155',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: '0.75rem',
      color: '#e2e8f0',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.name}</div>
      <div style={{ color: '#94a3b8' }}>
        적중률: <span style={{ color: hitRateColor(d.hit_rate) }}>{d.hit_rate.toFixed(1)}%</span>
      </div>
      <div style={{ color: '#94a3b8' }}>신호수: {d.signal_count}</div>
    </div>
  )
}

// ────────────────────────────────────────
// 섹션 헤더
// ────────────────────────────────────────

function SectionDivider({ title }: { title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
      <span style={{ color: '#94a3b8', fontSize: '0.78rem', fontWeight: 600, whiteSpace: 'nowrap' }}>
        {title}
      </span>
      <div style={{ flex: 1, height: 1, background: '#1e293b' }} />
    </div>
  )
}

// ────────────────────────────────────────
// 메인 컴포넌트
// ────────────────────────────────────────

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
const HORIZONS: number[] = [4, 8, 24]

export function AutoBacktest() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [horizonH, setHorizonH] = useState(24)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleRun() {
    setLoading(true)
    setError(null)
    apiFetch(`/api/sim/auto-backtest?symbol=${symbol}&horizon_h=${horizonH}&lookback=500`)
      .then((data) => {
        setResult(data as BacktestResult)
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : '백테스트 조회 실패'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }

  const chartData = result
    ? result.indicators.filter((ind) => ind.signal_count > 0)
    : []

  return (
    <div style={{ marginTop: 32 }}>
      <SectionDivider title="자동 백테스트" />

      {/* 컨트롤 바 */}
      <div style={{
        background: '#0f172a',
        border: '1px solid #1e293b',
        borderRadius: 10,
        padding: '14px 20px',
        marginBottom: 12,
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 12,
      }}>
        {/* 심볼 선택 */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>심볼:</span>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 6,
              color: '#e2e8f0',
              fontSize: '0.82rem',
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        {/* 수평선 선택 */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>수평선:</span>
          <select
            value={horizonH}
            onChange={(e) => setHorizonH(Number(e.target.value))}
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 6,
              color: '#e2e8f0',
              fontSize: '0.82rem',
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            {HORIZONS.map((h) => (
              <option key={h} value={h}>{h}h</option>
            ))}
          </select>
        </label>

        {/* 분석 실행 버튼 */}
        <button
          onClick={handleRun}
          disabled={loading}
          style={{
            padding: '5px 16px',
            borderRadius: 6,
            border: '1px solid #3b82f6',
            background: loading ? '#1e293b' : 'rgba(59,130,246,0.15)',
            color: loading ? '#475569' : '#60a5fa',
            fontSize: '0.82rem',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          분석 실행
        </button>

        {/* 로딩 표시 */}
        {loading && (
          <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>로딩 중...</span>
        )}

        {/* 메타 정보 */}
        {result && !loading && (
          <span style={{ color: '#64748b', fontSize: '0.75rem', marginLeft: 4 }}>
            데이터: {result.lookback_bars}봉 기준
            {' '}&nbsp;|&nbsp;{result.from_cache ? '캐시됨' : '신규 계산'}
            {' '}&nbsp;|&nbsp;갱신: {result.computed_at.slice(0, 16).replace('T', ' ')}
          </span>
        )}
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div style={{
          background: 'rgba(248,113,113,0.1)',
          border: '1px solid #f87171',
          borderRadius: 8,
          padding: '10px 16px',
          color: '#f87171',
          fontSize: '0.85rem',
          marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      {/* 결과 테이블 */}
      {result && (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          overflow: 'hidden',
          marginBottom: 16,
        }}>
          {/* 테이블 헤더 */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1.4fr 60px 50px 50px 70px 80px 110px',
            padding: '10px 16px',
            borderBottom: '1px solid #1e293b',
            background: '#0f172a',
          }}>
            {['지표', '신호수', '롱', '숏', '적중률', '평균수익', '최대익/손'].map((col) => (
              <div key={col} style={{
                color: '#64748b',
                fontSize: '0.7rem',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}>
                {col}
              </div>
            ))}
          </div>

          {/* 테이블 행 */}
          {result.indicators.map((ind, idx) => (
            <div
              key={ind.name}
              style={{
                display: 'grid',
                gridTemplateColumns: '1.4fr 60px 50px 50px 70px 80px 110px',
                padding: '9px 16px',
                borderBottom: idx < result.indicators.length - 1 ? '1px solid #1e293b' : 'none',
                background: idx % 2 === 0 ? '#0f172a' : 'rgba(30,41,59,0.3)',
                alignItems: 'center',
              }}
            >
              <div style={{ color: '#e2e8f0', fontSize: '0.82rem', fontWeight: 500 }}>
                {ind.name}
              </div>

              {ind.signal_count === 0 ? (
                <div style={{
                  gridColumn: '2 / 8',
                  color: '#475569',
                  fontSize: '0.78rem',
                  fontStyle: 'italic',
                }}>
                  데이터 부족
                </div>
              ) : (
                <>
                  <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>{ind.signal_count}</div>
                  <div style={{ color: '#4ade80', fontSize: '0.78rem' }}>{ind.long_signals}</div>
                  <div style={{ color: '#f87171', fontSize: '0.78rem' }}>{ind.short_signals}</div>
                  <div style={{ color: hitRateColor(ind.hit_rate), fontSize: '0.82rem', fontWeight: 600 }}>
                    {ind.hit_rate.toFixed(0)}%
                  </div>
                  <div style={{
                    color: ind.avg_return_pct >= 0 ? '#4ade80' : '#f87171',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                  }}>
                    {ind.avg_return_pct >= 0 ? '+' : ''}{ind.avg_return_pct.toFixed(2)}%
                  </div>
                  <div style={{ fontSize: '0.73rem' }}>
                    <span style={{ color: '#4ade80' }}>+{ind.max_win_pct.toFixed(1)}</span>
                    <span style={{ color: '#64748b' }}>/</span>
                    <span style={{ color: '#f87171' }}>{ind.max_loss_pct.toFixed(1)}%</span>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Recharts 바 차트 */}
      {result && chartData.length > 0 && (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          padding: '16px 20px',
          marginBottom: 12,
        }}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <XAxis
                dataKey="name"
                tick={{ fill: '#475569', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: '#475569', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `${v}%`}
                width={36}
              />
              <Tooltip content={<BacktestTooltip />} />
              <ReferenceLine
                y={50}
                stroke="#64748b"
                strokeDasharray="3 3"
                label={{ value: '50%', fill: '#64748b', fontSize: 10 }}
              />
              <Bar dataKey="hit_rate" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={hitRateColor(entry.hit_rate)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 면책 문구 */}
      <div style={{ color: '#64748b', fontSize: '0.72rem', marginTop: 8 }}>
        ⚠️ 과거 데이터 기반 통계입니다. 미래 수익을 보장하지 않습니다.
      </div>
    </div>
  )
}
