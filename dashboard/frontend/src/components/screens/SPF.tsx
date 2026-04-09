import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import { StatRow } from '../shared/StatRow'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'

interface SpfCurrent {
  date: string
  oi: number | null
  fr: number | null
  oi_change_3d: number
  oi_change_7d: number
  cum_fr_3d: number
  cum_fr_7d: number
  flow: string
  bearish_score: number
  bullish_score: number
  oi_consecutive_up: number
  oi_surge_alert: string | null
}

interface SimilarPattern {
  date: string
  similarity: number
  flow: string
  change_3d_pct: number
  bearish_score: number
}

interface TodayPrediction {
  direction: string
  confidence: number
  up_prob: number
  down_prob: number
  reasons: string  // JSON string
}

interface PredStats {
  total: number
  hits: number
  accuracy_pct: number | null
}

interface SpfData {
  current: SpfCurrent | null
  history: SpfCurrent[]
  similar_patterns: SimilarPattern[]
  today_prediction: TodayPrediction | null
}

interface PredHistory {
  predictions: Array<{
    date: string
    direction: string
    confidence: number
    result: string | null
    up_prob: number
    down_prob: number
  }>
  stats: PredStats
}

const FLOW_LABELS: Record<string, string> = {
  long_entry: '롱 신규 진입',
  short_entry: '숏 신규 진입',
  long_exit: '롱 청산',
  short_exit: '숏 청산',
  neutral: '중립',
}

const FLOW_COLORS: Record<string, string> = {
  long_entry: '#f97316',
  short_entry: '#60a5fa',
  long_exit: '#f87171',
  short_exit: '#4ade80',
  neutral: '#94a3b8',
}

function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{label}</span>
        <span style={{ color, fontWeight: 700, fontSize: '1.1rem' }}>{score}</span>
      </div>
      <div style={{ height: 8, background: '#334155', borderRadius: 4 }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: 4, transition: 'width 0.5s' }} />
      </div>
    </div>
  )
}

export function SPF() {
  const { data, loading, error, refetch, lastUpdated } = useApi<SpfData>('/api/spf-data', 120_000)
  const { data: predData } = useApi<PredHistory>('/api/prediction-history')

  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (loading || !data) return <Skeleton />

  const { current, history, similar_patterns, today_prediction } = data
  let reasons: string[] = []
  try {
    reasons = today_prediction?.reasons ? JSON.parse(today_prediction.reasons) : []
  } catch {
    reasons = []
  }

  const directionColor = today_prediction?.direction === '상승' ? '#4ade80'
    : today_prediction?.direction === '하락' ? '#f87171' : '#94a3b8'

  // 히스토리 차트 데이터 (오래된 순)
  const chartData = [...(history || [])].reverse().slice(-30).map(r => ({
    date: r.date?.slice(5),
    bearish: r.bearish_score,
    bullish: r.bullish_score,
    oi_change: +(r.oi_change_3d * 100).toFixed(2),
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} />
      {/* OI 급등 경고 배너 */}
      {current?.oi_surge_alert && (
        <div style={{
          background: current.oi_surge_alert === 'CRITICAL' ? 'rgba(239,68,68,0.15)' : 'rgba(249,115,22,0.15)',
          border: `1px solid ${current.oi_surge_alert === 'CRITICAL' ? '#ef4444' : '#f97316'}`,
          borderRadius: 8, padding: '10px 16px',
          color: current.oi_surge_alert === 'CRITICAL' ? '#f87171' : '#fb923c',
          fontWeight: 600, fontSize: '0.9rem',
        }}>
          ⚠️ OI {current.oi_surge_alert === 'CRITICAL' ? '급등 경고' : '주의'} — 3일 {(current.oi_change_3d * 100).toFixed(1)}% 상승
        </div>
      )}

      {/* 상단: 점수 카드 + 예측 */}
      <div className="grid-3" style={{ gap: 12 }}>
        {/* 하락 위험 점수 */}
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>하락 위험 점수</div>
          <ScoreBar label="하락 위험" score={current?.bearish_score ?? 0} color="#f87171" />
          <ScoreBar label="반등 기대" score={current?.bullish_score ?? 0} color="#4ade80" />
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <span style={{
              padding: '3px 10px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
              background: FLOW_COLORS[current?.flow ?? 'neutral'] + '33',
              color: FLOW_COLORS[current?.flow ?? 'neutral'],
            }}>
              {FLOW_LABELS[current?.flow ?? 'neutral']}
            </span>
            {(current?.oi_consecutive_up ?? 0) > 0 && (
              <span style={{ padding: '3px 10px', borderRadius: 12, fontSize: '0.75rem', background: '#334155', color: '#94a3b8' }}>
                OI {current?.oi_consecutive_up}일 연속↑
              </span>
            )}
          </div>
        </Card>

        {/* 오늘 예측 */}
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>3일 예측</div>
          {today_prediction ? (
            <>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: directionColor, marginBottom: 4 }}>
                {today_prediction.direction === '상승' ? '↑' : today_prediction.direction === '하락' ? '↓' : '→'} {today_prediction.direction}
              </div>
              <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: 12 }}>
                신뢰도 {today_prediction.confidence}%
              </div>
              {/* 확률 바 */}
              <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                <div style={{ width: `${today_prediction.up_prob}%`, background: '#4ade80' }} />
                <div style={{ width: `${today_prediction.down_prob}%`, background: '#f87171' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#94a3b8' }}>
                <span style={{ color: '#4ade80' }}>상승 {today_prediction.up_prob}%</span>
                <span style={{ color: '#f87171' }}>하락 {today_prediction.down_prob}%</span>
              </div>
            </>
          ) : (
            <div style={{ color: '#64748b', fontSize: '0.85rem' }}>예측 데이터 없음</div>
          )}
        </Card>

        {/* 성적표 */}
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>누적 적중률</div>
          {predData?.stats.accuracy_pct != null ? (
            <>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: predData.stats.accuracy_pct >= 60 ? '#4ade80' : '#f87171' }}>
                {predData.stats.accuracy_pct}%
              </div>
              <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: 4 }}>
                {predData.stats.total}전 {predData.stats.hits}승
              </div>
            </>
          ) : (
            <div style={{ color: '#64748b', fontSize: '0.85rem' }}>데이터 축적 중</div>
          )}
        </Card>
      </div>

      {/* 예측 근거 */}
      {reasons.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>예측 근거</div>
          <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {reasons.map((r, i) => (
              <li key={i} style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>{r}</li>
            ))}
          </ul>
        </Card>
      )}

      {/* 지표 패널 */}
      <div className="grid-2" style={{ gap: 12 }}>
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>OI 지표</div>
          <StatRow label="현재 OI" value={current?.oi ? `$${(current.oi / 1e9).toFixed(2)}B` : '—'} />
          <StatRow
            label="3일 변화"
            value={`${(current?.oi_change_3d ?? 0) > 0 ? '+' : ''}${((current?.oi_change_3d ?? 0) * 100).toFixed(2)}%`}
            highlight={(current?.oi_change_3d ?? 0) > 0.10 ? 'down' : (current?.oi_change_3d ?? 0) < -0.05 ? 'up' : 'neutral'}
          />
          <StatRow label="7일 변화" value={`${((current?.oi_change_7d ?? 0) * 100).toFixed(2)}%`} />
          <StatRow label="연속 상승" value={`${current?.oi_consecutive_up ?? 0}일`} />
        </Card>
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>FR 지표</div>
          <StatRow
            label="현재 FR"
            value={`${((current?.fr ?? 0) * 100).toFixed(4)}%`}
            highlight={(current?.fr ?? 0) > 0.0003 ? 'down' : (current?.fr ?? 0) < -0.0001 ? 'up' : 'neutral'}
          />
          <StatRow label="3일 누적 FR" value={`${((current?.cum_fr_3d ?? 0) * 100).toFixed(4)}%`} />
          <StatRow label="7일 누적 FR" value={`${((current?.cum_fr_7d ?? 0) * 100).toFixed(4)}%`} />
          <StatRow label="흐름 유형" value={FLOW_LABELS[current?.flow ?? 'neutral']} />
        </Card>
      </div>

      {/* 점수 히스토리 차트 */}
      {chartData.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>하락위험/반등 점수 추이 (30일)</div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={chartData}>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <ReferenceLine y={70} stroke="#f87171" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="bearish" stroke="#f87171" dot={false} strokeWidth={2} name="하락위험" />
              <Line type="monotone" dataKey="bullish" stroke="#4ade80" dot={false} strokeWidth={2} name="반등기대" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* 유사 패턴 TOP5 */}
      {similar_patterns.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>유사 패턴 TOP {similar_patterns.length}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {similar_patterns.map((p, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', background: '#0f1117', borderRadius: 8 }}>
                <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{p.date}</span>
                <span style={{ color: '#60a5fa', fontSize: '0.8rem' }}>{p.similarity}%</span>
                <span style={{ color: FLOW_COLORS[p.flow] || '#94a3b8', fontSize: '0.8rem' }}>{FLOW_LABELS[p.flow] || p.flow}</span>
                <span style={{ color: p.change_3d_pct > 0 ? '#4ade80' : '#f87171', fontWeight: 600, fontSize: '0.8rem' }}>
                  {p.change_3d_pct > 0 ? '+' : ''}{p.change_3d_pct}%
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 최근 예측 기록 */}
      {predData && predData.predictions.length > 0 && (
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 10 }}>최근 예측 기록</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {predData.predictions.slice(0, 10).map((p, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 8px', background: '#0f1117', borderRadius: 6 }}>
                <span style={{ color: '#64748b', fontSize: '0.78rem', width: 80 }}>{p.date}</span>
                <span style={{ color: p.direction === '상승' ? '#4ade80' : p.direction === '하락' ? '#f87171' : '#94a3b8', fontSize: '0.8rem', width: 50 }}>{p.direction}</span>
                <span style={{ color: '#64748b', fontSize: '0.78rem', width: 60 }}>신뢰 {p.confidence}%</span>
                <span style={{
                  fontSize: '0.75rem', fontWeight: 600, padding: '2px 8px', borderRadius: 10,
                  background: p.result === 'hit' ? 'rgba(74,222,128,0.15)' : p.result === 'miss' ? 'rgba(248,113,113,0.15)' : 'rgba(100,116,139,0.15)',
                  color: p.result === 'hit' ? '#4ade80' : p.result === 'miss' ? '#f87171' : '#64748b',
                }}>
                  {p.result === 'hit' ? '✓ 적중' : p.result === 'miss' ? '✗ 미스' : '판정중'}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

    </div>
  )
}
