import { Fragment, useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiFetch } from '../../lib/api'
import { useIsMobile } from '../../hooks/useIsMobile'
import LastUpdated from '../shared/LastUpdated'
import { C, changeColor, softBg } from '../../lib/theme'
import { fmtFixed, fmtSignedPct } from '../../lib/format'
import { directionText } from './leaderboardView'

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

// 샤프 — 음수 부호를 다른 수치(fmtSignedPct)와 같은 U+2212로
const sharpeText = (v: number) => fmtFixed(v, 2).replace('-', '\u2212')

// 방향 칸 — 자산별 포지션을 글로 요약. 상승·하락 색은 ▲▼와 함께 쓴다
function DirectionText({ directions }: { directions?: Record<string, 'long' | 'short'> }) {
  const { text, tone } = directionText(directions ?? {})
  const color = tone === 'up' ? 'var(--up)' : tone === 'down' ? 'var(--down)' : 'var(--text)'
  return (
    <span style={{ color, fontWeight: 600 }}>
      {tone !== 'flat' && <span aria-hidden="true">{tone === 'up' ? '▲' : '▼'} </span>}
      {text}
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
  const [resetting, setResetting] = useState(false)
  const isMobile = useIsMobile()

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
    setResetting(true)
    try {
      await apiFetch('/api/sim/leaderboard/reset', { method: 'POST' })
      setSelected(null)
      setDetail(null)
      await fetchBoard()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '리셋 실패')
    } finally {
      setResetting(false)
    }
  }

  // 선택 지표의 상세(에쿼티 곡선·포지션 이력) — PC는 표 아래, 모바일은 선택 카드 바로 아래
  const detailPanel = selected && (
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
                <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis tick={{ fill: C.text3, fontSize: 11 }} width={50} domain={['auto', 'auto']} />
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
  )

  return (
    <div>
      <LastUpdated timestamp={loadedAt} />
      <p className="leaderboard-toolbar-copy">
        지표마다 같은 가상 자금으로 자기 신호대로 자동매매한 성과입니다. 수익률이 높은 순으로 정렬됩니다.
      </p>

      {loading ? (
        <div style={PANEL}>로딩 중...</div>
      ) : error ? (
        <div style={{ ...PANEL, color: 'var(--danger)' }}>{error}</div>
      ) : rows.length === 0 ? (
        <div style={{ ...PANEL, color: 'var(--text-2)' }}>
          아직 데이터가 없습니다. 일일 리밸런스 잡(UTC 00:05)이 1회 이상 실행되면 표시됩니다.
        </div>
      ) : isMobile ? (
        <div className="leaderboard-cards">
          {rows.map((r, i) => (
            <Fragment key={r.indicator}>
            <button
              type="button"
              className="leaderboard-card"
              aria-pressed={selected === r.indicator}
              aria-expanded={selected === r.indicator}
              onClick={() => (selected === r.indicator ? setSelected(null) : fetchDetail(r.indicator))}
            >
              <span className="leaderboard-card-head">
                <span className="leaderboard-card-name">
                  <span className="leaderboard-card-rank" style={{ color: i < 3 ? 'var(--accent)' : 'var(--text-3)' }}>{i + 1}</span>
                  <span>{r.indicator}</span>
                </span>
                <span className="leaderboard-card-ret" style={{ color: changeColor(r.total_return_pct) }}>
                  {fmtSignedPct(r.total_return_pct)}
                </span>
              </span>
              <span className="leaderboard-card-sub">
                <span>지금 방향 <DirectionText directions={r.directions} /></span>
                <span>매수보유 대비 <span className="leaderboard-card-num" style={{ color: changeColor(r.vs_buyhold_pct) }}>{fmtSignedPct(r.vs_buyhold_pct)}</span></span>
              </span>
              <span className="leaderboard-card-stats">
                <span><span>승률</span><span>{r.win_rate == null ? '—' : `${fmtFixed(r.win_rate, 0)}%`}</span></span>
                <span><span>최대 낙폭</span><span style={{ color: 'var(--down)' }}>{fmtSignedPct(r.mdd_pct, 1)}</span></span>
                <span><span>샤프</span><span>{sharpeText(r.sharpe)}</span></span>
                <span><span>거래</span><span>{r.n_trades}</span></span>
              </span>
            </button>
            {selected === r.indicator && detailPanel}
            </Fragment>
          ))}
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
                  <td style={{ textAlign: 'center', padding: '8px 6px' }}><DirectionText directions={r.directions} /></td>
                  <td style={{ padding: '8px 6px', color: changeColor(r.total_return_pct), fontWeight: 600, ...MONO }}>{pct(r.total_return_pct)}</td>
                  <td style={{ padding: '8px 6px', color: changeColor(r.vs_buyhold_pct), ...MONO }}>{pct(r.vs_buyhold_pct)}</td>
                  <td style={{ padding: '8px 6px', color: 'var(--text-2)', ...MONO }}>{r.win_rate == null ? '–' : `${r.win_rate.toFixed(0)}%`}</td>
                  <td style={{ padding: '8px 6px', color: 'var(--down)', ...MONO }}>{r.mdd_pct.toFixed(1)}%</td>
                  <td style={{ padding: '8px 6px', color: 'var(--text-2)', ...MONO }}>{sharpeText(r.sharpe)}</td>
                  <td style={{ padding: '8px 6px', color: 'var(--text-3)', ...MONO }}>{r.n_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {!isMobile && detailPanel}

      <div className="leaderboard-reset">
        <button type="button" className="leaderboard-reset-button" onClick={handleReset} disabled={resetting}>
          처음 자금으로 리셋
        </button>
        <span className="leaderboard-reset-note">모든 지표의 성과 기록이 지워집니다. 누르면 한 번 더 확인합니다.</span>
      </div>
    </div>
  )
}
