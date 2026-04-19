import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { apiFetch } from '../../lib/api'

// ────────────────────────────────────────
// 타입 정의
// ────────────────────────────────────────

interface ScorecardSummary {
  total: number
  hits: number
  hit_rate: number
  avg_pnl: number | null
  liquidations: number
}

interface IndicatorStat {
  indicator: string
  count: number
  hits: number
  hit_rate: number
}

interface SettledPrediction {
  id: number
  asset_symbol: string
  mode: string
  direction: string | null
  entry_price: number
  expiry_time: string
  indicator_tags: string[]
  status: string
}

interface SimScorecardProps {
  market?: 'crypto' | 'kr_stock' | 'us_stock'
}

// ────────────────────────────────────────
// 섹션 헤더 컴포넌트
// ────────────────────────────────────────

function SectionDivider({ title }: { title: string }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginBottom: 14,
    }}>
      <span style={{ color: '#94a3b8', fontSize: '0.78rem', fontWeight: 600, whiteSpace: 'nowrap' }}>
        {title}
      </span>
      <div style={{ flex: 1, height: 1, background: '#1e293b' }} />
    </div>
  )
}

// ────────────────────────────────────────
// 커스텀 Tooltip
// ────────────────────────────────────────

function BarTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: IndicatorStat }> }) {
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
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.indicator}</div>
      <div style={{ color: '#94a3b8' }}>적중률: <span style={{ color: '#60a5fa' }}>{d.hit_rate.toFixed(1)}%</span></div>
      <div style={{ color: '#94a3b8' }}>건수: {d.hits}/{d.count}</div>
    </div>
  )
}

// ────────────────────────────────────────
// 메인 스코어카드 컴포넌트
// ────────────────────────────────────────

export function SimScorecard({ market }: SimScorecardProps) {
  const [summary, setSummary] = useState<ScorecardSummary | null>(null)
  const [indicators, setIndicators] = useState<IndicatorStat[]>([])
  const [predictions, setPredictions] = useState<SettledPrediction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const marketQuery = market ? `?market=${market}` : ''
    const marketParam = market ? `market=${market}&` : ''

    setLoading(true)
    setError(null)

    Promise.all([
      apiFetch(`/api/sim/scorecard${marketQuery}`),
      apiFetch(`/api/sim/scorecard/by-indicator${marketQuery}`),
      apiFetch(`/api/sim/predictions?${marketParam}status=settled`),
    ])
      .then(([summaryData, indicatorData, predData]) => {
        setSummary(summaryData as ScorecardSummary)
        setIndicators((indicatorData as IndicatorStat[]).slice(0, 10))
        setPredictions((predData as SettledPrediction[]).slice(0, 20))
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : '스코어카드 조회 실패'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [market])

  if (loading) {
    return (
      <div style={{ color: '#94a3b8', fontSize: '0.875rem', padding: '24px 0' }}>
        스코어카드 로딩 중...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ color: '#f87171', fontSize: '0.875rem', padding: '24px 0' }}>
        {error}
      </div>
    )
  }

  const hasSummary = summary && summary.total > 0
  const hasIndicators = indicators.length > 0
  const hasPredictions = predictions.length > 0

  return (
    <div style={{ marginTop: 32 }}>
      {/* ── 스코어카드 요약 ── */}
      <SectionDivider title="스코어카드" />

      {!hasSummary ? (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          padding: '24px',
          textAlign: 'center',
          color: '#94a3b8',
          fontSize: '0.875rem',
          marginBottom: 24,
        }}>
          데이터 없음
        </div>
      ) : (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          padding: '16px 20px',
          marginBottom: 24,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 24,
          alignItems: 'center',
        }}>
          {/* 전체 적중률 */}
          <div>
            <div style={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
              전체 적중률
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#60a5fa' }}>
                {summary.hit_rate.toFixed(0)}%
              </span>
              <span style={{ color: '#64748b', fontSize: '0.8rem' }}>
                ({summary.hits}/{summary.total}건)
              </span>
            </div>
          </div>

          {/* 구분선 */}
          <div style={{ width: 1, height: 36, background: '#1e293b' }} />

          {/* 평균 PnL */}
          <div>
            <div style={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
              평균 PnL
            </div>
            <div style={{
              fontSize: '1.1rem',
              fontWeight: 700,
              color: summary.avg_pnl == null
                ? '#94a3b8'
                : summary.avg_pnl >= 0 ? '#4ade80' : '#f87171',
            }}>
              {summary.avg_pnl == null
                ? '-'
                : (summary.avg_pnl >= 0 ? '+' : '') + summary.avg_pnl.toFixed(1) + '%'}
            </div>
          </div>

          {/* 구분선 */}
          <div style={{ width: 1, height: 36, background: '#1e293b' }} />

          {/* 청산 건수 */}
          <div>
            <div style={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
              청산
            </div>
            <div style={{
              fontSize: '1.1rem',
              fontWeight: 700,
              color: summary.liquidations > 0 ? '#f87171' : '#94a3b8',
            }}>
              {summary.liquidations}건
            </div>
          </div>
        </div>
      )}

      {/* ── 지표별 적중률 ── */}
      <SectionDivider title="지표별 적중률" />

      {!hasIndicators ? (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          padding: '24px',
          textAlign: 'center',
          color: '#94a3b8',
          fontSize: '0.875rem',
          marginBottom: 24,
        }}>
          데이터 없음
        </div>
      ) : (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          padding: '16px 20px',
          marginBottom: 24,
        }}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={indicators} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <XAxis
                dataKey="indicator"
                tick={{ fill: '#475569', fontSize: 11 }}
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
              <Tooltip content={<BarTooltip />} />
              <ReferenceLine y={50} stroke="#475569" strokeDasharray="3 3" strokeOpacity={0.6} />
              <Bar dataKey="hit_rate" fill="#60a5fa" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── 예측 히스토리 테이블 ── */}
      <SectionDivider title="예측 히스토리" />

      {!hasPredictions ? (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          padding: '24px',
          textAlign: 'center',
          color: '#94a3b8',
          fontSize: '0.875rem',
        }}>
          데이터 없음
        </div>
      ) : (
        <div style={{
          background: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: 10,
          overflow: 'hidden',
        }}>
          {/* 테이블 헤더 */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 80px 60px 100px 100px 1fr',
            padding: '10px 16px',
            borderBottom: '1px solid #1e293b',
            background: '#0f172a',
          }}>
            {['자산', '모드', '방향', '진입가', '만료일', '지표'].map(col => (
              <div key={col} style={{ color: '#64748b', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {col}
              </div>
            ))}
          </div>

          {/* 테이블 행 */}
          {predictions.map((pred, idx) => (
            <div
              key={pred.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 80px 60px 100px 100px 1fr',
                padding: '10px 16px',
                borderBottom: idx < predictions.length - 1 ? '1px solid #1e293b' : 'none',
                background: idx % 2 === 0 ? '#0f172a' : 'rgba(30,41,59,0.3)',
                alignItems: 'center',
              }}
            >
              {/* 자산 */}
              <div style={{ color: '#e2e8f0', fontSize: '0.85rem', fontWeight: 600 }}>
                {pred.asset_symbol}
              </div>

              {/* 모드 */}
              <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                {{
                  direction: '방향성',
                  target_price: '목표가',
                  portfolio: '포트폴리오',
                }[pred.mode] ?? pred.mode}
              </div>

              {/* 방향 */}
              <div>
                {pred.direction ? (
                  <span style={{
                    padding: '2px 6px',
                    borderRadius: 3,
                    background: pred.direction === 'long' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
                    color: pred.direction === 'long' ? '#4ade80' : '#f87171',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                  }}>
                    {pred.direction === 'long' ? '롱' : '숏'}
                  </span>
                ) : (
                  <span style={{ color: '#475569', fontSize: '0.78rem' }}>-</span>
                )}
              </div>

              {/* 진입가 */}
              <div style={{ color: '#e2e8f0', fontSize: '0.78rem' }}>
                {pred.entry_price.toLocaleString()}
              </div>

              {/* 만료일 */}
              <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                {pred.expiry_time.slice(0, 10)}
              </div>

              {/* 지표 태그 */}
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {pred.indicator_tags && pred.indicator_tags.length > 0
                  ? pred.indicator_tags.map(tag => (
                    <span
                      key={tag}
                      style={{
                        padding: '1px 6px',
                        borderRadius: 3,
                        background: '#1e293b',
                        color: '#94a3b8',
                        fontSize: '0.68rem',
                      }}
                    >
                      {tag}
                    </span>
                  ))
                  : <span style={{ color: '#475569', fontSize: '0.78rem' }}>-</span>
                }
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
