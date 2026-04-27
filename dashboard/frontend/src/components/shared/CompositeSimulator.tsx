import { useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { apiFetch } from '../../lib/api'

// ────────────────────────────────────────
// 날짜 유틸
// ────────────────────────────────────────

function toDateString(date: Date): string {
  return date.toISOString().split('T')[0]
}

function getDefaultDates(): { startDate: string; endDate: string } {
  const today = new Date()
  const thirtyDaysAgo = new Date(today)
  thirtyDaysAgo.setDate(today.getDate() - 30)
  return {
    startDate: toDateString(thirtyDaysAgo),
    endDate: toDateString(today),
  }
}

// ────────────────────────────────────────
// 타입 정의
// ────────────────────────────────────────

interface TradeSummary {
  total_return_pct: number
  win_rate: number        // 0~1
  trade_count: number
  winning_trades: number
  losing_trades: number
  max_drawdown_pct: number  // 음수
  final_capital: number
}

interface TradeEntry {
  type: 'buy' | 'sell'
  timestamp: string
  price: number
  pnl_pct: number | null
  reason: string | null
  composite_score: number
}

interface EquityPoint {
  timestamp: string
  value: number
}

interface BacktestParams {
  symbol: string
  interval: string
  start_date: string
  end_date: string
  stop_loss_pct: number
  take_profit_pct: number
  macro_level: string
  macro_bullish_score: number
}

interface CompositeResult {
  summary: TradeSummary
  trades: TradeEntry[]
  equity_curve: EquityPoint[]
  params: BacktestParams
}

// ────────────────────────────────────────
// 상수
// ────────────────────────────────────────

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
const INTERVALS = ['1h', '4h', '1d']

const REASON_MAP: Record<string, string> = {
  stop_loss: '손절',
  take_profit: '익절',
  score_signal: '시그널',
  period_end: '기간종료',
}

// ────────────────────────────────────────
// 섹션 구분선
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
// 요약 카드 컴포넌트
// ────────────────────────────────────────

interface SummaryCardProps {
  label: string
  value: string
  sub?: string
  valueColor?: string
}

function SummaryCard({ label, value, sub, valueColor }: SummaryCardProps) {
  return (
    <div style={{
      background: '#111827',
      border: '1px solid #1e293b',
      borderRadius: 10,
      padding: '14px 18px',
      flex: 1,
      minWidth: 0,
    }}>
      <div style={{ color: '#94a3b8', fontSize: '0.72rem', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div style={{ color: valueColor ?? '#f1f5f9', fontSize: '1.25rem', fontWeight: 700 }}>
        {value}
      </div>
      {sub && (
        <div style={{ color: '#475569', fontSize: '0.72rem', marginTop: 4 }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────
// 커스텀 Tooltip (자본 곡선)
// ────────────────────────────────────────

interface EquityTooltipPayload {
  payload?: { timestamp: string; value: number }
  active?: boolean
  // recharts는 payload를 배열로 전달하므로 두 가지 형태 허용
}

function EquityTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: EquityPoint }> }) {
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
      <div style={{ color: '#94a3b8', marginBottom: 2 }}>{d.timestamp.slice(0, 10)}</div>
      <div style={{ fontWeight: 600 }}>${d.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
    </div>
  )
}

// ────────────────────────────────────────
// select 공통 스타일
// ────────────────────────────────────────

const selectStyle: React.CSSProperties = {
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: '0.82rem',
  padding: '4px 8px',
  cursor: 'pointer',
}

const inputStyle: React.CSSProperties = {
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: '0.82rem',
  padding: '4px 8px',
  outline: 'none',
  width: 130,
}

const numberInputStyle: React.CSSProperties = {
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: '0.82rem',
  padding: '4px 8px',
  outline: 'none',
  width: 64,
}

// ────────────────────────────────────────
// 메인 컴포넌트
// ────────────────────────────────────────

const { startDate: defaultStart, endDate: defaultEnd } = getDefaultDates()

export function CompositeSimulator() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setInterval] = useState('1h')
  const [startDate, setStartDate] = useState(defaultStart)
  const [endDate, setEndDate] = useState(defaultEnd)
  const [stopLoss, setStopLoss] = useState(3.0)
  const [takeProfit, setTakeProfit] = useState(5.0)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CompositeResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  function handleRun() {
    if (loading) return
    setLoading(true)
    setError(null)

    apiFetch<CompositeResult>('/api/sim/composite-backtest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol,
        interval,
        start_date: startDate,
        end_date: endDate,
        stop_loss_pct: stopLoss,
        take_profit_pct: takeProfit,
      }),
    })
      .then((data) => setResult(data))
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : '백테스트 실패'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }

  // 요약 값 계산
  const summary = result?.summary
  const totalReturnPct = summary?.total_return_pct ?? 0
  const returnColor = totalReturnPct >= 0 ? '#22c55e' : '#ef4444'
  const returnStr = `${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%`
  const winRatePct = summary ? (summary.win_rate * 100).toFixed(1) : '0.0'
  const winLossSub = summary ? `${summary.winning_trades}승 ${summary.losing_trades}패` : ''

  // 자본 곡선 초기 자본 (첫 번째 값)
  const initialCapital = result?.equity_curve?.[0]?.value ?? 10000

  // 표시할 거래 내역 (최대 50개)
  const displayTrades = result?.trades.slice(0, 50) ?? []

  return (
    <div style={{ marginTop: 32 }}>
      <SectionDivider title="종합 자동 백테스트" />

      {/* ── 설정 패널 ── */}
      <div style={{
        background: '#111827',
        border: '1px solid #1e293b',
        borderRadius: 10,
        padding: '16px 20px',
        marginBottom: 16,
      }}>
        {/* 행 1: 심볼, 캔들, 기간 */}
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 14,
          marginBottom: 12,
        }}>
          {/* 심볼 */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>심볼:</span>
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} style={selectStyle}>
              {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>

          {/* 캔들 */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>캔들:</span>
            <select value={interval} onChange={(e) => setInterval(e.target.value)} style={selectStyle}>
              {INTERVALS.map((iv) => <option key={iv} value={iv}>{iv}</option>)}
            </select>
          </label>

          {/* 기간 */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>기간:</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={inputStyle}
            />
            <span style={{ color: '#475569', fontSize: '0.78rem' }}>~</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={inputStyle}
            />
          </label>
        </div>

        {/* 행 2: 손절/익절, 실행 버튼 */}
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 14,
        }}>
          {/* 손절 */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>손절:</span>
            <input
              type="number"
              value={stopLoss}
              step={0.5}
              min={0.1}
              onChange={(e) => setStopLoss(Number(e.target.value))}
              style={numberInputStyle}
            />
            <span style={{ color: '#475569', fontSize: '0.78rem' }}>%</span>
          </label>

          {/* 익절 */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>익절:</span>
            <input
              type="number"
              value={takeProfit}
              step={0.5}
              min={0.1}
              onChange={(e) => setTakeProfit(Number(e.target.value))}
              style={numberInputStyle}
            />
            <span style={{ color: '#475569', fontSize: '0.78rem' }}>%</span>
          </label>

          {/* 실행 버튼 */}
          <button
            onClick={handleRun}
            disabled={loading}
            style={{
              marginLeft: 'auto',
              padding: '6px 20px',
              borderRadius: 6,
              border: '1px solid #3b82f6',
              background: loading ? '#1e293b' : 'rgba(59,130,246,0.15)',
              color: loading ? '#475569' : '#60a5fa',
              fontSize: '0.85rem',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            {loading ? '분석 중...' : '🚀 테스트 실행'}
          </button>
        </div>
      </div>

      {/* ── 에러 박스 ── */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid #ef4444',
          borderRadius: 8,
          padding: '10px 16px',
          color: '#ef4444',
          fontSize: '0.85rem',
          marginBottom: 14,
        }}>
          {error}
        </div>
      )}

      {/* ── 결과 패널 ── */}
      {result && (
        <>
          {/* 요약 카드 3개 */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <SummaryCard
              label="총 수익률"
              value={returnStr}
              sub={`MDD ${result.summary.max_drawdown_pct.toFixed(2)}%`}
              valueColor={returnColor}
            />
            <SummaryCard
              label="승률"
              value={`${winRatePct}%`}
              sub={winLossSub}
            />
            <SummaryCard
              label="거래 횟수"
              value={`${result.summary.trade_count}회`}
              sub={`최종 자본 $${result.summary.final_capital.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
            />
          </div>

          {/* 자본 곡선 */}
          {result.equity_curve.length > 0 && (
            <div style={{
              background: '#111827',
              border: '1px solid #1e293b',
              borderRadius: 10,
              padding: '16px 20px',
              marginBottom: 16,
            }}>
              <div style={{ color: '#94a3b8', fontSize: '0.78rem', marginBottom: 10, fontWeight: 600 }}>
                자본 곡선
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={result.equity_curve} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <XAxis
                    dataKey="timestamp"
                    tick={{ fill: '#475569', fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v: string) => v.slice(5, 10)}  // MM-DD 형식
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: '#475569', fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
                    width={44}
                  />
                  <Tooltip content={<EquityTooltip />} />
                  <ReferenceLine
                    y={initialCapital}
                    stroke="#475569"
                    strokeDasharray="4 4"
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#60a5fa"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 매크로 정보 배지 */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 14,
            flexWrap: 'wrap',
          }}>
            <span style={{
              background: 'rgba(96,165,250,0.12)',
              border: '1px solid rgba(96,165,250,0.3)',
              borderRadius: 6,
              padding: '3px 10px',
              color: '#93c5fd',
              fontSize: '0.75rem',
              fontWeight: 600,
            }}>
              현재 매크로: {result.params.macro_level} (강세점수 {result.params.macro_bullish_score})
            </span>
            <span style={{ color: '#475569', fontSize: '0.68rem' }}>
              * 매크로 점수는 현재 시점 기준 정적 적용
            </span>
          </div>

          {/* 거래 내역 테이블 */}
          <div style={{
            background: '#111827',
            border: '1px solid #1e293b',
            borderRadius: 10,
            overflow: 'hidden',
            marginBottom: 12,
          }}>
            {/* 테이블 헤더 */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1.6fr 56px 1.1fr 80px 80px 70px',
              padding: '10px 16px',
              borderBottom: '1px solid #1e293b',
              background: '#0f1117',
            }}>
              {['날짜', '유형', '가격', '수익률', '사유', '점수'].map((col) => (
                <div key={col} style={{
                  color: '#64748b',
                  fontSize: '0.68rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}>
                  {col}
                </div>
              ))}
            </div>

            {/* 거래 없음 */}
            {displayTrades.length === 0 ? (
              <div style={{
                padding: '20px 16px',
                color: '#475569',
                fontSize: '0.82rem',
                textAlign: 'center',
              }}>
                거래 없음
              </div>
            ) : (
              displayTrades.map((trade, idx) => {
                const isBuy = trade.type === 'buy'
                const pnlColor = trade.pnl_pct === null
                  ? '#94a3b8'
                  : trade.pnl_pct >= 0 ? '#22c55e' : '#ef4444'
                const pnlStr = trade.pnl_pct === null
                  ? '-'
                  : `${trade.pnl_pct >= 0 ? '+' : ''}${trade.pnl_pct.toFixed(2)}%`
                const reasonStr = trade.reason ? (REASON_MAP[trade.reason] ?? trade.reason) : '-'

                return (
                  <div
                    key={idx}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1.6fr 56px 1.1fr 80px 80px 70px',
                      padding: '8px 16px',
                      borderBottom: idx < displayTrades.length - 1 ? '1px solid #1e293b' : 'none',
                      background: idx % 2 === 0 ? '#111827' : 'rgba(30,41,59,0.25)',
                      alignItems: 'center',
                    }}
                  >
                    {/* 날짜 */}
                    <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
                      {trade.timestamp.slice(0, 16).replace('T', ' ')}
                    </div>

                    {/* 유형 */}
                    <div style={{
                      color: isBuy ? '#22c55e' : pnlColor,
                      fontSize: '0.78rem',
                      fontWeight: 600,
                    }}>
                      {isBuy ? '🟢 매수' : '🔴 매도'}
                    </div>

                    {/* 가격 */}
                    <div style={{ color: '#f1f5f9', fontSize: '0.78rem' }}>
                      ${trade.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </div>

                    {/* 수익률 */}
                    <div style={{ color: pnlColor, fontSize: '0.78rem', fontWeight: 600 }}>
                      {pnlStr}
                    </div>

                    {/* 사유 */}
                    <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
                      {reasonStr}
                    </div>

                    {/* 점수 */}
                    <div style={{ color: '#60a5fa', fontSize: '0.75rem' }}>
                      {trade.composite_score.toFixed(1)}
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {/* 최대 50개 제한 안내 */}
          {(result.trades.length > 50) && (
            <div style={{ color: '#475569', fontSize: '0.72rem', marginBottom: 8 }}>
              * 상위 50개 거래만 표시 (전체 {result.trades.length}개)
            </div>
          )}
        </>
      )}

      {/* 면책 문구 */}
      <div style={{ color: '#475569', fontSize: '0.72rem', marginTop: 8 }}>
        ⚠️ 과거 데이터 기반 시뮬레이션입니다. 미래 수익을 보장하지 않습니다.
      </div>
    </div>
  )
}
