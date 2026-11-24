import { Link } from 'react-router-dom'
import { fmtCoinPrice, fmtFixed, fmtSignedPct } from '../../lib/format'
import { changeArrow, changeColor } from '../../lib/theme'
import type { BotNewsItem, DiffRow, Ladder, SignalCell } from './homeBriefView'

// 홈 머리 구역 — 신호판, 비트코인 청산 구간 막대, 어제와 달라진 것, 봇이 보낸 소식
// 스펙: docs/plans/light-redesign-spec-2026-11-24.md 6절

// 분석 신호판: 점수 분석 카테고리마다 한 칸 (누르면 리서치)
export function SignalBoard({ cells, tally, loading }: { cells: SignalCell[]; tally: string; loading: boolean }) {
  return (
    <section className="signal-board" aria-label="분석 신호판">
      <div className="signal-board-head">
        <strong>분석 {cells.length > 0 ? `${cells.length}개 ` : ''}신호판</strong>
        <span>{tally || (loading ? '분석을 불러오는 중입니다' : '분석 결과가 없습니다')}</span>
      </div>
      <div className="signal-grid">
        {cells.map(cell => (
          <Link key={cell.key} to="/research" className="signal-cell" data-level={cell.level}>
            <span className="signal-cell-bar" />
            <span className="signal-cell-text">
              <span className="signal-cell-name">{cell.name}</span>
              <span className="signal-cell-level">{cell.label}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  )
}

// 비트코인 현재가 + 아래 롱·위 숏 청산 구간 사이 위치
export function BtcLadder({ price, change, ladder }: { price: number | null; change: number | null; ladder: Ladder | null }) {
  return (
    <section className="btc-ladder" aria-label="비트코인">
      <span className="btc-ladder-title">비트코인</span>
      <div className="btc-ladder-price">
        <strong>{fmtCoinPrice(price)}</strong>
        {change != null && (
          <span style={{ color: changeColor(change) }}>{changeArrow(change)} {fmtFixed(Math.abs(change), 2)}%</span>
        )}
      </div>
      {ladder ? (
        <>
          <span className="btc-ladder-cap">큰 청산 구간 사이에서 지금 위치</span>
          <div
            className="btc-ladder-track"
            role="img"
            aria-label={`현재가는 아래 롱 청산 구간과 위 숏 청산 구간 사이 ${Math.round(ladder.percent)}% 지점`}
          >
            <i style={{ width: `${ladder.percent}%` }} />
            <b />
            <i style={{ flex: 1 }} />
          </div>
          <div className="btc-ladder-ends">
            <span className="btc-ladder-end">
              <span>아래 큰 롱 청산 구간</span>
              <strong>{fmtCoinPrice(ladder.long)}</strong>
              <span>{fmtSignedPct(ladder.longGap, 1)}</span>
            </span>
            <span className="btc-ladder-end">
              <span>위 큰 숏 청산 구간</span>
              <strong>{fmtCoinPrice(ladder.short)}</strong>
              <span>{fmtSignedPct(ladder.shortGap, 1)}</span>
            </span>
          </div>
        </>
      ) : (
        <span className="btc-ladder-cap">청산 구간은 봇이 히트맵 숫자를 보내면 표시됩니다</span>
      )}
    </section>
  )
}

// 어제와 달라진 것: 등급 · 이름 · 요약 · 어제 → 오늘 점수
export function DiffList({ rows, loading }: { rows: DiffRow[]; loading: boolean }) {
  return (
    <section aria-labelledby="home-diff-title">
      <div className="home-sec-head">
        <h2 id="home-diff-title">어제와 달라진 것</h2>
        <Link to="/research" className="home-sec-link">리서치 전체 ›</Link>
      </div>
      {rows.length === 0 && <div className="home-empty">{loading ? '분석을 불러오는 중입니다' : '분석 결과가 없습니다'}</div>}
      {rows.map(row => (
        <Link key={row.key} to="/research" className="home-row">
          <span className="lv" data-level={row.level}>{row.label}</span>
          <span className="home-row-name">{row.name}</span>
          <span className="home-row-text">{row.summary}</span>
          <span className="home-row-delta">{row.delta}</span>
        </Link>
      ))}
    </section>
  )
}

// 봇이 보낸 소식: 시각 · 이름 · 요약
export function BotNews({ items }: { items: BotNewsItem[] }) {
  if (items.length === 0) return null
  return (
    <section aria-labelledby="home-bot-title">
      <div className="home-sec-head">
        <h2 id="home-bot-title">봇이 보낸 소식</h2>
        <Link to="/bot-reports" className="home-sec-link">봇 리포트 ›</Link>
      </div>
      {items.map(item => (
        <Link key={item.key} to="/bot-reports" className="home-news">
          <span className="home-news-time">{item.time}</span>
          <span className="home-news-body">
            <strong>{item.name}</strong>
            <span>{item.summary}</span>
          </span>
        </Link>
      ))}
    </section>
  )
}
