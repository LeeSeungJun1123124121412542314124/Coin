import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'

// ────────────────────────────────────────
// 타입 정의 (백엔드 backtest_tuner 결과 스키마와 일치)
// ────────────────────────────────────────

interface OOSMetrics {
  expectancy: number
  profit_factor: number
  max_drawdown_pct: number
  win_rate: number
  trade_count: number
  avg_win_pct?: number
  avg_loss_pct?: number
  total_return_pct?: number
}

interface TopCombination {
  window_index: number
  params: Record<string, number>
  metrics: OOSMetrics
}

interface AggregateResult {
  passes_filter: boolean
  n_windows: number
  avg_oos_expectancy: number
  avg_oos_profit_factor: number
  avg_oos_mdd: number
  avg_oos_win_rate: number
  avg_oos_trade_count: number
  top_combinations: TopCombination[]
}

interface JobProgress {
  current_window: number
  total_windows: number
  current_trial: number
  total_trials: number
}

interface TuningJob {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  started_at?: string
  completed_at?: string | null
  progress?: JobProgress
  windows?: Array<{
    index: number
    is_period: { start: string; end: string }
    oos_period: { start: string; end: string }
    best_params: Record<string, number>
    oos_metrics: OOSMetrics
  }>
  aggregate?: AggregateResult
  error?: string
}

// ────────────────────────────────────────
// Props
// ────────────────────────────────────────

export interface TuningParamsForReplay {
  long_threshold: number
  short_threshold: number
  score_exit_buffer: number
  stop_loss_pct: number
  take_profit_pct: number
  position_size_pct: number
  leverage: number
}

interface TuningResultTableProps {
  symbol: string
  interval: string
  startDate: string
  endDate: string
  initialCapital: number
  onSelectParams?: (params: TuningParamsForReplay) => void
}

// ────────────────────────────────────────
// 스타일
// ────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  background: '#111827',
  border: '1px solid #1e293b',
  borderRadius: 10,
  padding: '16px 20px',
  marginBottom: 12,
}

const inputStyle: React.CSSProperties = {
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: '0.82rem',
  padding: '4px 8px',
  outline: 'none',
  width: 80,
}

// ────────────────────────────────────────
// 메인 컴포넌트
// ────────────────────────────────────────

export function TuningResultTable({
  symbol,
  interval,
  startDate,
  endDate,
  initialCapital,
  onSelectParams,
}: TuningResultTableProps) {
  const [nTrials, setNTrials] = useState(200)
  const [nWindows, setNWindows] = useState(9)
  const [job, setJob] = useState<TuningJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 폴링 정리
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [])

  function stopPolling() {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  function startPolling(jobId: string) {
    stopPolling()
    pollTimerRef.current = setInterval(async () => {
      try {
        const data = await apiFetch<TuningJob>(`/api/sim/tune/${jobId}`)
        setJob(data)
        if (data.status === 'completed' || data.status === 'failed') {
          stopPolling()
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : '폴링 실패'
        setError(msg)
        stopPolling()
      }
    }, 5000)
  }

  async function handleStart() {
    setError(null)
    setJob(null)
    try {
      const res = await apiFetch<{ job_id: string; status: string }>('/api/sim/tune', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          interval,
          start_date: startDate,
          end_date: endDate,
          initial_capital: initialCapital,
          n_trials: nTrials,
          n_windows: nWindows,
        }),
      })
      setJob({ job_id: res.job_id, status: 'queued' })
      // 즉시 1회 조회 후 폴링 시작
      const first = await apiFetch<TuningJob>(`/api/sim/tune/${res.job_id}`).catch(() => null)
      if (first) setJob(first)
      startPolling(res.job_id)
    } catch (e) {
      const msg = e instanceof Error ? e.message : '튜닝 시작 실패'
      setError(msg)
    }
  }

  const isRunning = job?.status === 'queued' || job?.status === 'running'
  const progress = job?.progress
  const aggregate = job?.aggregate
  const top = aggregate?.top_combinations ?? []

  return (
    <div style={{ marginTop: 8 }}>
      {/* ── 시작 패널 ── */}
      <div style={cardStyle}>
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 14,
        }}>
          <span style={{ color: '#cbd5e1', fontSize: '0.85rem', fontWeight: 600 }}>
            🔬 자동 튜닝 (Walk-Forward)
          </span>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>윈도우당 trials:</span>
            <input
              type="number"
              value={nTrials}
              step={50}
              min={20}
              max={1000}
              onChange={(e) => setNTrials(Number(e.target.value))}
              disabled={isRunning}
              style={inputStyle}
            />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>윈도우 수:</span>
            <input
              type="number"
              value={nWindows}
              step={1}
              min={3}
              max={12}
              onChange={(e) => setNWindows(Number(e.target.value))}
              disabled={isRunning}
              style={inputStyle}
            />
          </label>
          <button
            onClick={handleStart}
            disabled={isRunning}
            style={{
              padding: '6px 18px',
              borderRadius: 6,
              border: `1px solid ${isRunning ? '#1e293b' : '#a855f7'}`,
              background: isRunning ? '#0f1117' : 'rgba(168,85,247,0.15)',
              color: isRunning ? '#334155' : '#c084fc',
              fontSize: '0.85rem',
              cursor: isRunning ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              marginLeft: 'auto',
            }}
          >
            {isRunning ? '🔄 실행 중...' : '🚀 자동 튜닝 시작'}
          </button>
        </div>
        <div style={{ color: '#64748b', fontSize: '0.72rem', marginTop: 6 }}>
          전체 기간({startDate} ~ {endDate})을 expanding window로 분할해 IS에서 최적
          파라미터를 찾고 OOS로 검증합니다. 12개 파라미터(임계값/SL·TP/포지션/가중치)를
          Optuna TPE로 탐색.
        </div>
      </div>

      {/* ── 에러 ── */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid #b91c1c',
          borderRadius: 8,
          padding: '10px 14px',
          color: '#fca5a5',
          marginBottom: 12,
          fontSize: '0.8rem',
        }}>
          ⚠ {error}
        </div>
      )}

      {/* ── 진행률 ── */}
      {isRunning && progress && (
        <div style={cardStyle}>
          <div style={{ color: '#cbd5e1', fontSize: '0.8rem', marginBottom: 8 }}>
            진행: Window {progress.current_window}/{progress.total_windows}, Trial{' '}
            {progress.current_trial}/{progress.total_trials}
          </div>
          <div style={{ background: '#1e293b', borderRadius: 4, height: 8, overflow: 'hidden' }}>
            <div
              style={{
                width: `${
                  progress.total_windows > 0
                    ? (((progress.current_window - 1) / progress.total_windows) +
                        (progress.current_trial / progress.total_trials / progress.total_windows)) *
                      100
                    : 0
                }%`,
                background: 'linear-gradient(90deg, #a855f7, #60a5fa)',
                height: '100%',
                transition: 'width 0.4s ease',
              }}
            />
          </div>
        </div>
      )}

      {/* ── 결과 요약 ── */}
      {job?.status === 'completed' && aggregate && (
        <>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
              <div style={{
                padding: '6px 14px',
                borderRadius: 999,
                background: aggregate.passes_filter ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                color: aggregate.passes_filter ? '#86efac' : '#fca5a5',
                fontSize: '0.85rem',
                fontWeight: 700,
              }}>
                {aggregate.passes_filter ? '✅ 필터 통과' : '❌ 필터 미통과'}
              </div>
              <Metric label="OOS 평균 Expectancy"
                value={`${aggregate.avg_oos_expectancy >= 0 ? '+' : ''}${aggregate.avg_oos_expectancy.toFixed(3)}`}
                color={aggregate.avg_oos_expectancy > 0 ? '#22c55e' : '#ef4444'} />
              <Metric label="OOS 평균 PF"
                value={aggregate.avg_oos_profit_factor.toFixed(2)}
                color={aggregate.avg_oos_profit_factor >= 1.5 ? '#22c55e' : '#94a3b8'} />
              <Metric label="OOS 평균 MDD"
                value={`${aggregate.avg_oos_mdd.toFixed(2)}%`}
                color={aggregate.avg_oos_mdd <= 25 ? '#22c55e' : '#ef4444'} />
              <Metric label="OOS 평균 승률"
                value={`${(aggregate.avg_oos_win_rate * 100).toFixed(1)}%`} />
              <Metric label="OOS 평균 거래수"
                value={String(aggregate.avg_oos_trade_count)} />
              <Metric label="윈도우 수"
                value={`${aggregate.n_windows}`} />
            </div>
          </div>

          {/* ── 상위 10 조합 테이블 ── */}
          <div style={cardStyle}>
            <div style={{ color: '#cbd5e1', fontSize: '0.85rem', fontWeight: 600, marginBottom: 10 }}>
              상위 {top.length}개 필터 통과 조합 (행 클릭 시 단일 백테스트로 재현)
            </div>
            {top.length === 0 ? (
              <div style={{ color: '#64748b', fontSize: '0.8rem' }}>
                필터(PF≥1.5, MDD≤25%, 거래수≥30)를 통과하는 조합이 없습니다.
                튜닝 trial 수를 늘리거나 신호 체계 자체를 재검토해야 합니다.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                  <thead>
                    <tr style={{ color: '#94a3b8', borderBottom: '1px solid #1e293b' }}>
                      <th style={th}>#</th>
                      <th style={th}>Win</th>
                      <th style={th}>Expectancy</th>
                      <th style={th}>PF</th>
                      <th style={th}>MDD%</th>
                      <th style={th}>승률</th>
                      <th style={th}>거래수</th>
                      <th style={th}>L_th</th>
                      <th style={th}>S_th</th>
                      <th style={th}>SL%</th>
                      <th style={th}>TP%</th>
                      <th style={th}>Buf</th>
                      <th style={th}>Pos%</th>
                      <th style={th}>Lev</th>
                      <th style={th}>MW</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((c, idx) => (
                      <tr
                        key={idx}
                        onClick={() => onSelectParams?.({
                          long_threshold: Number(c.params.long_threshold),
                          short_threshold: Number(c.params.short_threshold),
                          score_exit_buffer: Number(c.params.score_exit_buffer),
                          stop_loss_pct: Number(c.params.stop_loss_pct),
                          take_profit_pct: Number(c.params.take_profit_pct),
                          position_size_pct: Number(c.params.position_size_pct),
                          leverage: Number(c.params.leverage),
                        })}
                        style={{
                          color: '#e2e8f0',
                          borderBottom: '1px solid #1e293b',
                          cursor: onSelectParams ? 'pointer' : 'default',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = '#1e293b')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <td style={td}>{idx + 1}</td>
                        <td style={td}>{c.window_index}</td>
                        <td style={{ ...td, color: c.metrics.expectancy > 0 ? '#86efac' : '#fca5a5' }}>
                          {c.metrics.expectancy.toFixed(3)}
                        </td>
                        <td style={td}>{c.metrics.profit_factor.toFixed(2)}</td>
                        <td style={td}>{c.metrics.max_drawdown_pct.toFixed(1)}</td>
                        <td style={td}>{(c.metrics.win_rate * 100).toFixed(1)}%</td>
                        <td style={td}>{c.metrics.trade_count}</td>
                        <td style={td}>{c.params.long_threshold}</td>
                        <td style={td}>{c.params.short_threshold}</td>
                        <td style={td}>{Number(c.params.stop_loss_pct).toFixed(1)}</td>
                        <td style={td}>{Number(c.params.take_profit_pct).toFixed(1)}</td>
                        <td style={td}>{c.params.score_exit_buffer}</td>
                        <td style={td}>{Number(c.params.position_size_pct).toFixed(0)}</td>
                        <td style={td}>{c.params.leverage}</td>
                        <td style={td}>{Number(c.params.macro_weight).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── 실패 ── */}
      {job?.status === 'failed' && (
        <div style={{
          ...cardStyle,
          border: '1px solid #b91c1c',
          color: '#fca5a5',
        }}>
          ❌ 튜닝 실패: {job.error ?? '알 수 없는 오류'}
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────
// 작은 metric 표시 컴포넌트
// ────────────────────────────────────────

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ color: '#94a3b8', fontSize: '0.7rem', marginBottom: 2 }}>{label}</div>
      <div style={{ color: color ?? '#f1f5f9', fontWeight: 700, fontSize: '0.95rem' }}>{value}</div>
    </div>
  )
}

const th: React.CSSProperties = {
  textAlign: 'left',
  padding: '6px 8px',
  fontWeight: 600,
}

const td: React.CSSProperties = {
  padding: '6px 8px',
  whiteSpace: 'nowrap',
}
