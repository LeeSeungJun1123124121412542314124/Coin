import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiFetch } from '../../lib/api'
import LastUpdated from '../shared/LastUpdated'
import { C, changeColor, softBg } from '../../lib/theme'

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
  directions: Record<string, 'long' | 'short'>  // 현재 열린 포지션 방향(자산별), 현금 자산은 생략
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
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  boxShadow: 'var(--shadow-card)',
  borderRadius: 16,
  padding: '18px 20px',
  marginBottom: 20,
}

function pct(v: number | null): string {
  if (v == null) return '–'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

// 숫자 칸 공통 — Mono
const MONO: CSSProperties = { fontFamily: 'var(--font-mono)' }

// 자산별 방향 배지 (BTC·ETH·SOL) — 롱=--up·숏=--down·현금=--surface-2 바탕 대시
const ASSETS = ['BTC', 'ETH', 'SOL'] as const
function DirectionBadges({ directions = {} }: { directions?: Record<string, 'long' | 'short'> }) {
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      {ASSETS.map((a) => {
        const d = directions[a]
        const color = d === 'long' ? C.up : d === 'short' ? C.down : C.text3
        const bg = d === 'long' ? softBg(C.up, 0.14) : d === 'short' ? softBg(C.down, 0.14) : C.surface2
        const label = d === 'long' ? '롱' : d === 'short' ? '숏' : '–'
        return (
          <span
            key={a}
            title={`${a} ${d === 'long' ? '롱' : d === 'short' ? '숏' : '현금'}`}
            style={{
              display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
              minWidth: 24, fontSize: '0.6rem', lineHeight: 1.3,
            }}
          >
            <span style={{ color: 'var(--text-3)' }}>{a[0]}</span>
            <span style={{ color, background: bg, borderRadius: 6, padding: '1px 6px', fontWeight: 600 }}>{label}</span>
          </span>
        )
      })}
    </span>
  )
}

export function Leaderboard() {
  const [rows, setRows] = useState<LeaderRow[]>([])
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)
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
      setLoadedAt(new Date())
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
      <LastUpdated timestamp={loadedAt} />
      <div className="leaderboard-toolbar">
        <p className="leaderboard-toolbar-copy">
          💰 <b>지표 수익 검증</b> — 각 지표가 동일 시드로 자기 신호대로 자동매매, 포워드 성과(수익)로 어느 지표가 실제 돈이 되나 비교.
          <span style={{ color: 'var(--text-3)' }}> 시장 방향 전망은 SPF 탭에서.</span>
        </p>
        <button
          className="leaderboard-reset-button"
          onClick={handleReset}
        >
          시드 리셋
        </button>
      </div>

      {loading ? (
        <div style={PANEL}>로딩 중...</div>
      ) : error ? (
        <div style={{ ...PANEL, color: 'var(--danger)' }}>{error}</div>
      ) : rows.length === 0 ? (
        <div style={{ ...PANEL, color: 'var(--text-2)' }}>
          아직 데이터가 없습니다. 일일 리밸런스 잡(UTC 00:05)이 1회 이상 실행되면 표시됩니다.
        </div>
      ) : (
        <div style={PANEL}>
          {/* 9컬럼 테이블 — 모바일 가로 스크롤(잘림 방지) */}
          <div className="table-scroll">
          <table style={{ width: '100%', minWidth: 640, borderCollapse: 'collapse', fontSize: '0.85rem', whiteSpace: 'nowrap' }}>
            <thead>
              <tr style={{ color: 'var(--text-3)', textAlign: 'right', borderBottom: '1px solid var(--line)' }}>
                <th style={{ textAlign: 'left', padding: '8px 6px' }}>#</th>
                <th style={{ textAlign: 'left', padding: '8px 6px' }}>지표</th>
                <th style={{ textAlign: 'center', padding: '8px 6px' }}>방향</th>
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
                    borderBottom: '1px solid var(--line)',
                    background: selected === r.indicator ? softBg(C.accent, 0.07) : 'transparent',
                  }}
                >
                  <td style={{ textAlign: 'left', padding: '8px 6px', color: i < 3 ? 'var(--accent)' : 'var(--text-3)', fontWeight: i < 3 ? 700 : 400, ...MONO }}>{i + 1}</td>
                  <td style={{ textAlign: 'left', padding: '8px 6px', color: 'var(--text)', fontWeight: 600 }}>{r.indicator}</td>
                  <td style={{ textAlign: 'center', padding: '8px 6px' }}><DirectionBadges directions={r.directions} /></td>
                  <td style={{ padding: '8px 6px', color: changeColor(r.total_return_pct), fontWeight: 600, ...MONO }}>{pct(r.total_return_pct)}</td>
                  <td style={{ padding: '8px 6px', color: changeColor(r.vs_buyhold_pct), ...MONO }}>{pct(r.vs_buyhold_pct)}</td>
                  <td style={{ padding: '8px 6px', color: 'var(--text-2)', ...MONO }}>{r.win_rate == null ? '–' : `${r.win_rate.toFixed(0)}%`}</td>
                  <td style={{ padding: '8px 6px', color: 'var(--down)', ...MONO }}>{r.mdd_pct.toFixed(1)}%</td>
                  <td style={{ padding: '8px 6px', color: 'var(--text-2)', ...MONO }}>{r.sharpe.toFixed(2)}</td>
                  <td style={{ padding: '8px 6px', color: 'var(--text-3)', ...MONO }}>{r.n_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {selected && (
        <div style={PANEL}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginTop: 0 }}>
            {selected} — 에쿼티 곡선
          </h3>
          {detailLoading ? (
            <div style={{ color: 'var(--text-2)' }}>로딩 중...</div>
          ) : !detail || detail.equity_curve.length === 0 ? (
            <div style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>곡선 데이터 없음</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={detail.equity_curve}>
                  <CartesianGrid stroke={C.line} strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 9 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: C.text3, fontSize: 10 }} width={50} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, color: C.text }}
                  />
                  <Line type="monotone" dataKey="equity" stroke={C.accent} dot={false} strokeWidth={2} name="에쿼티" />
                </LineChart>
              </ResponsiveContainer>

              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)', marginTop: 16 }}>포지션 이력</h3>
              {/* 7컬럼 테이블 — 모바일 가로 스크롤(잘림 방지) */}
              <div className="table-scroll">
              <table style={{ width: '100%', minWidth: 520, borderCollapse: 'collapse', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                <thead>
                  <tr style={{ color: 'var(--text-3)', textAlign: 'right', borderBottom: '1px solid var(--line)' }}>
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
                    <tr key={i} style={{ textAlign: 'right', borderBottom: '1px solid var(--line)' }}>
                      <td style={{ textAlign: 'left', padding: '6px', color: 'var(--text)' }}>{p.asset}</td>
                      <td style={{ textAlign: 'left', padding: '6px', color: p.direction === 'long' ? 'var(--up)' : 'var(--down)' }}>
                        {p.direction === 'long' ? '롱' : '숏'}
                      </td>
                      <td style={{ padding: '6px', color: 'var(--text-2)', ...MONO }}>{p.leverage.toFixed(1)}x</td>
                      <td style={{ padding: '6px', color: 'var(--text-2)', ...MONO }}>{p.entry_price.toFixed(2)}</td>
                      <td style={{ padding: '6px', color: 'var(--text-2)', ...MONO }}>{p.exit_price == null ? '–' : p.exit_price.toFixed(2)}</td>
                      <td style={{ padding: '6px', color: changeColor(p.pnl), ...MONO }}>{p.pnl == null ? '–' : p.pnl.toFixed(2)}</td>
                      <td style={{ padding: '6px', color: 'var(--text-3)' }}>{p.status === 'open' ? '보유' : '청산'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
