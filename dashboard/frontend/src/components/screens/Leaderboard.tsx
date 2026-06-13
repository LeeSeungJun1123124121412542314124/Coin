import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiFetch } from '../../lib/api'

// 지표 리더보드 — 각 지표가 가상 시드로 자동매매한 포워드 성과 순위
interface LeaderRow {
  indicator: string
  total_return_pct: number
  win_rate: number | null
  mdd_pct: number
  sharpe: number
  vs_buyhold_pct: number | null
  n_trades: number
  capital: number
  seed: number
  equity: number
}

interface Position {
  asset: string
  direction: 'long' | 'short'
  qty: number
  entry_price: number
  leverage: number
  liq_price: number | null
  opened_at: string
  closed_at: string | null
  exit_price: number | null
  pnl: number | null
  status: 'open' | 'closed'
}

interface Detail {
  indicator: string
  seed: number
  capital: number
  equity_curve: { date: string; equity: number; return_pct: number | null }[]
  positions: Position[]
}

const PANEL: CSSProperties = {
  background: '#0f172a',
  border: '1px solid #1e293b',
  borderRadius: 10,
  padding: '16px 20px',
  marginBottom: 20,
}

function pct(v: number | null): string {
  if (v == null) return '–'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

function clr(v: number | null): string {
  if (v == null) return '#94a3b8'
  return v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8'
}

export function Leaderboard() {
  const [rows, setRows] = useState<LeaderRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchBoard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data: { leaderboard: LeaderRow[] } = await apiFetch('/api/sim/leaderboard')
      setRows(data.leaderboard)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '리더보드 조회 실패')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchDetail = useCallback(async (indicator: string) => {
    setSelected(indicator)
    setDetailLoading(true)
    try {
      const d: Detail = await apiFetch(`/api/sim/leaderboard/${encodeURIComponent(indicator)}`)
      setDetail(d)
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBoard()
  }, [fetchBoard])

  const handleReset = async () => {
    if (!window.confirm('모든 지표 포트폴리오를 시드로 리셋합니다. 계속할까요?')) return
    try {
      await apiFetch('/api/sim/leaderboard/reset', { method: 'POST' })
      setSelected(null)
      setDetail(null)
      await fetchBoard()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '리셋 실패')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0 }}>
          각 지표가 동일 시드로 자기 신호대로 자동매매 — 포워드(미래 미관측) 성과로 실전 쓸모를 검증
        </p>
        <button
          onClick={handleReset}
          style={{
            padding: '6px 14px', borderRadius: 8, border: '1px solid #334155',
            background: '#0f172a', color: '#94a3b8', cursor: 'pointer', fontSize: '0.8rem',
          }}
        >
          시드 리셋
        </button>
      </div>

      {loading ? (
        <div style={PANEL}>로딩 중...</div>
      ) : error ? (
        <div style={{ ...PANEL, color: '#f87171' }}>{error}</div>
      ) : rows.length === 0 ? (
        <div style={{ ...PANEL, color: '#94a3b8' }}>
          아직 데이터가 없습니다. 일일 리밸런스 잡(UTC 00:05)이 1회 이상 실행되면 표시됩니다.
        </div>
      ) : (
        <div style={PANEL}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ color: '#64748b', textAlign: 'right', borderBottom: '1px solid #1e293b' }}>
                <th style={{ textAlign: 'left', padding: '8px 6px' }}>#</th>
                <th style={{ textAlign: 'left', padding: '8px 6px' }}>지표</th>
                <th style={{ padding: '8px 6px' }}>총수익</th>
                <th style={{ padding: '8px 6px' }}>vs매수보유</th>
                <th style={{ padding: '8px 6px' }}>승률</th>
                <th style={{ padding: '8px 6px' }}>MDD</th>
                <th style={{ padding: '8px 6px' }}>Sharpe</th>
                <th style={{ padding: '8px 6px' }}>거래</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={r.indicator}
                  onClick={() => fetchDetail(r.indicator)}
                  style={{
                    textAlign: 'right', cursor: 'pointer',
                    borderBottom: '1px solid #1e293b',
                    background: selected === r.indicator ? '#1e293b' : 'transparent',
                  }}
                >
                  <td style={{ textAlign: 'left', padding: '8px 6px', color: '#64748b' }}>{i + 1}</td>
                  <td style={{ textAlign: 'left', padding: '8px 6px', color: '#e2e8f0', fontWeight: 600 }}>{r.indicator}</td>
                  <td style={{ padding: '8px 6px', color: clr(r.total_return_pct), fontWeight: 600 }}>{pct(r.total_return_pct)}</td>
                  <td style={{ padding: '8px 6px', color: clr(r.vs_buyhold_pct) }}>{pct(r.vs_buyhold_pct)}</td>
                  <td style={{ padding: '8px 6px', color: '#cbd5e1' }}>{r.win_rate == null ? '–' : `${r.win_rate.toFixed(0)}%`}</td>
                  <td style={{ padding: '8px 6px', color: '#f87171' }}>{r.mdd_pct.toFixed(1)}%</td>
                  <td style={{ padding: '8px 6px', color: '#cbd5e1' }}>{r.sharpe.toFixed(2)}</td>
                  <td style={{ padding: '8px 6px', color: '#64748b' }}>{r.n_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div style={PANEL}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e2e8f0', marginTop: 0 }}>
            {selected} — 에쿼티 곡선
          </h3>
          {detailLoading ? (
            <div style={{ color: '#94a3b8' }}>로딩 중...</div>
          ) : !detail || detail.equity_curve.length === 0 ? (
            <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>곡선 데이터 없음</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={detail.equity_curve}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={50} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, color: '#e2e8f0' }}
                  />
                  <Line type="monotone" dataKey="equity" stroke="#60a5fa" dot={false} strokeWidth={2} name="에쿼티" />
                </LineChart>
              </ResponsiveContainer>

              <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#e2e8f0', marginTop: 16 }}>포지션 이력</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr style={{ color: '#64748b', textAlign: 'right', borderBottom: '1px solid #1e293b' }}>
                    <th style={{ textAlign: 'left', padding: '6px' }}>자산</th>
                    <th style={{ textAlign: 'left', padding: '6px' }}>방향</th>
                    <th style={{ padding: '6px' }}>레버리지</th>
                    <th style={{ padding: '6px' }}>진입가</th>
                    <th style={{ padding: '6px' }}>청산/종료가</th>
                    <th style={{ padding: '6px' }}>실현PnL</th>
                    <th style={{ padding: '6px' }}>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.positions.slice(0, 50).map((p, i) => (
                    <tr key={i} style={{ textAlign: 'right', borderBottom: '1px solid #1e293b' }}>
                      <td style={{ textAlign: 'left', padding: '6px', color: '#e2e8f0' }}>{p.asset}</td>
                      <td style={{ textAlign: 'left', padding: '6px', color: p.direction === 'long' ? '#4ade80' : '#f87171' }}>
                        {p.direction === 'long' ? '롱' : '숏'}
                      </td>
                      <td style={{ padding: '6px', color: '#cbd5e1' }}>{p.leverage.toFixed(1)}x</td>
                      <td style={{ padding: '6px', color: '#cbd5e1' }}>{p.entry_price.toFixed(2)}</td>
                      <td style={{ padding: '6px', color: '#94a3b8' }}>{p.exit_price == null ? '–' : p.exit_price.toFixed(2)}</td>
                      <td style={{ padding: '6px', color: clr(p.pnl) }}>{p.pnl == null ? '–' : p.pnl.toFixed(2)}</td>
                      <td style={{ padding: '6px', color: '#64748b' }}>{p.status === 'open' ? '보유' : '청산'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  )
}
