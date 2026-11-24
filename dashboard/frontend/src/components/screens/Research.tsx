import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import ErrorState from '../shared/ErrorState'
import LastUpdated from '../shared/LastUpdated'
import { C, LEVEL_COLORS, changeArrow, changeColor } from '../../lib/theme'
import {
  LEVEL_LABELS,
  RESEARCH_CATEGORIES,
  STOCK_SENTIMENT_INDEX_NOTES,
  sortByUrgency,
  toCompareLines,
  toKrStockFlowDetailRows,
  toStockSentimentDetailRows,
} from './researchView'
import type { CategoryCompare } from './researchView'
import { signalTally, toSignalCells } from './homeBriefView'

interface CategoryAnalysis {
  key: string
  name: string
  level: string
  score: number
  title: string
  summary: string
  details: Record<string, unknown>
  updated_at: string
  compare?: CategoryCompare | null
  // 봇이 보낸 리포트로 만든 카드 — 점수·등급이 없다
  observed?: boolean
}

interface ResearchData {
  generated_at: string
  categories: CategoryAnalysis[]
}

// 줄 목록의 한 줄: 등급 · 이름 · 제목 · 요약, 오른쪽에 점수 (봇 관찰은 점수 없음)
function AnalysisCard({ cat, expanded, onToggle }: {
  cat: CategoryAnalysis
  expanded: boolean
  onToggle: () => void
}) {
  const levelLabel = LEVEL_LABELS[cat.level] ?? cat.level
  const time = cat.updated_at ? new Date(cat.updated_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : ''

  const details = cat.details as Record<string, unknown>
  const compareLines = toCompareLines(cat, LEVEL_LABELS)

  return (
    <div className="research-item" data-level={cat.level} onClick={onToggle}>
      {/* 머리: 등급 · 이름 · 제목 | 점수 */}
      <div className="research-item-top">
        <div className="research-item-main">
          <div className="research-item-meta">
            {cat.observed ? <span className="research-item-bot">봇 관찰</span> : <span className="lv">{levelLabel}</span>}
            <span className="research-item-name">{cat.name}</span>
            <span className="research-item-time">{time}</span>
          </div>
          <h3 className="research-item-title">{cat.title}</h3>
        </div>
        {/* 점수(위험도) — 봇 관찰 카드는 점수가 없다 */}
        {!cat.observed && (
          <div className="research-item-score" aria-label={`위험도 ${cat.score}/100`}>
            <span><strong>{cat.score}</strong><small>/100</small></span>
            <span className="research-item-bar"><i style={{ width: `${Math.min(100, Math.max(0, cat.score))}%` }} /></span>
          </div>
        )}
      </div>

      {/* 어제·7일 전 대비 — 이전 저장분이 있을 때만 */}
      {(compareLines.prevLine || compareLines.weekLine) && (
        <div className="research-item-text">
          {compareLines.prevLine && <div>{compareLines.prevLine}</div>}
          {compareLines.weekLine && <div style={{ color: 'var(--text-3)' }}>{compareLines.weekLine}</div>}
        </div>
      )}

      {/* 요약 — 이전 저장분이 있으면 오늘·이전 요약을 나란히 */}
      <div className="research-item-text">
        {compareLines.prevSummary ? (
          <>
            <div><span style={{ color: 'var(--text-3)' }}>오늘: </span>{cat.summary}</div>
            <div style={{ color: 'var(--text-3)' }}>{compareLines.prevSummary.label}: {compareLines.prevSummary.text}</div>
          </>
        ) : cat.summary}
      </div>

      {/* 상세 정보 (expanded) */}
      {expanded && Object.keys(details).length > 0 && (
        <div style={{
          marginTop: 8,
          paddingTop: 14,
          borderTop: '1px solid var(--line)',
        }}>
          {_renderDetails(cat.key, details)}
        </div>
      )}

      {/* 클릭은 줄의 onClick이 받는다 — 키보드·보조기기용 버튼 */}
      <button type="button" aria-expanded={expanded} className="research-detail-btn">
        {expanded ? '▲ 접기' : '▼ 상세'}
      </button>
    </div>
  )
}

function _renderDetails(key: string, details: Record<string, unknown>) {
  // 봇 관찰 카드 — 백엔드가 만들어 준 [이름, 값] 줄을 그대로 그린다
  if (Array.isArray(details.rows)) {
    const rows = details.rows as Array<[string, string]>
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rows.map(([label, value], i) => (
          <div key={i} style={{ fontSize: 12, lineHeight: 1.6, overflowWrap: 'anywhere' }}>
            <div style={{ color: 'var(--text-3)' }}>{label}</div>
            <div style={{ color: 'var(--text-2)', fontWeight: 600 }}>{value}</div>
          </div>
        ))}
        <Link to="/bot-reports" onClick={e => e.stopPropagation()} style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'underline' }}>
          원문 보기 (봇 리포트)
        </Link>
      </div>
    )
  }
  if (key === 'derivatives') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {[
          ['포지션 흐름', details.flow as string],
          ['하락 점수', `${details.bearish_score}/100`],
          ['반등 점수', `${details.bullish_score}/100`],
          ['OI 3일', `${details.oi_change_3d}%`],
          ['OI 7일', `${details.oi_change_7d}%`],
          ['FR 3일 누적', `${details.cum_fr_3d}%`],
        ].map(([label, value]) => value != null && (
          <div key={label as string} style={{ fontSize: 12 }}>
            <span style={{ color: 'var(--text-3)' }}>{label}: </span>
            <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{value}</span>
          </div>
        ))}
      </div>
    )
  }

  if (key === 'altcoin') {
    const coins = (details.coins as Array<{ symbol: string; change_24h: number }>) ?? []
    return (
      <div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4, marginBottom: 8 }}>
          {coins.map(c => (
            <div key={c.symbol} style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-2)' }}>{c.symbol} </span>
              <span style={{ color: changeColor(c.change_24h), fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {changeArrow(c.change_24h)} {c.change_24h >= 0 ? '+' : ''}{c.change_24h?.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
        {details.btc_dominance != null && (
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            BTC 도미넌스: <span style={{ color: 'var(--text-2)' }}>{String(details.btc_dominance)}%</span>
          </div>
        )}
      </div>
    )
  }

  if (key === 'macro') {
    const auctions = (details.upcoming_auctions as Array<{
      auction_date: string
      type: string
      term: string
      offering_amount_b: number | null
    }>) ?? []
    if (auctions.length === 0) {
      return <div style={{ fontSize: 12, color: 'var(--text-3)' }}>국채 경매 일정 없음 또는 수집 중</div>
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 4 }}>향후 국채 경매 (일부)</div>
        {auctions.slice(0, 8).map((a, i) => (
          <div key={i} style={{ fontSize: 12, color: 'var(--text-2)' }}>
            <span style={{ color: 'var(--text-2)' }}>{a.auction_date?.slice(0, 10)}</span>
            {' · '}{a.type} {a.term}
            {a.offering_amount_b != null && (
              <span style={{ color: 'var(--text-3)' }}> · {a.offering_amount_b}B$</span>
            )}
          </div>
        ))}
      </div>
    )
  }

  if (key === 'market') {
    const insights = (details.insights as Array<{ level: string; title: string; body: string }>) ?? []
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {insights.slice(0, 4).map((ins, i) => (
          <div key={i} style={{ fontSize: 12, color: 'var(--text-2)' }}>
            <span style={{ color: LEVEL_COLORS[ins.level] ?? C.text2, fontWeight: 600 }}>
              {ins.title}
            </span>
            {' — '}{ins.body}
          </div>
        ))}
      </div>
    )
  }

  if (key === 'stock_sentiment') {
    return (
      <div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {toStockSentimentDetailRows(details).map(([label, value]) => (
            <div key={label} style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-3)' }}>{label}: </span>
              <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{value}</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {STOCK_SENTIMENT_INDEX_NOTES.map(([name, note]) => (
            <div key={name} style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }}>
              <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{name}</span> — {note}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (key === 'kr_stock_flow') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {toKrStockFlowDetailRows(details).map(([label, value]) => (
          <div key={label} style={{ fontSize: 12 }}>
            <span style={{ color: 'var(--text-3)' }}>{label}: </span>
            <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{value}</span>
          </div>
        ))}
      </div>
    )
  }

  // 기본: key-value 나열
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
      {Object.entries(details)
        .filter(([, v]) => v != null && typeof v !== 'object')
        .map(([k, v]) => (
          <div key={k} style={{ fontSize: 12 }}>
            <span style={{ color: 'var(--text-3)' }}>{k}: </span>
            <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{String(v)}</span>
          </div>
        ))}
    </div>
  )
}

function SkeletonCard() {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-card)', padding: '18px 20px' }}>
      {[80, 140, 100, 20].map((w, i) => (
        <div key={i} style={{
          height: i === 0 ? 16 : i === 1 ? 14 : i === 2 ? 12 : 6,
          width: `${w}%`,
          background: 'var(--surface-2)',
          borderRadius: 4,
          marginBottom: i < 3 ? 10 : 0,
          animation: 'pulse 1.5s infinite',
        }} />
      ))}
    </div>
  )
}

export function Research() {
  const [activeCategory, setActiveCategory] = useState('전체')
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const { data, loading, error, refetch, lastUpdated } = useApi<ResearchData>('/api/research-analysis', 600_000)

  const categories = data?.categories ?? []
  const filtered = sortByUrgency(
    activeCategory === '전체' ? categories : categories.filter(c => c.name === activeCategory),
  )

  // 갱신 줄 요약: 위험·경계 건수 (0인 것은 뺀다)
  // 봇 관찰 카드는 점수가 없어 분석 건수·위험 집계에서 뺀다
  const scored = categories.filter(c => !c.observed)
  const scoredList = filtered.filter(c => !c.observed)
  const observedList = filtered.filter(c => c.observed)
  const observedCount = categories.length - scored.length
  const criticalCount = scored.filter(c => c.level === 'critical').length
  const warningCount = scored.filter(c => c.level === 'warning').length
  const alertParts = [
    ...(criticalCount > 0 ? [`위험 ${criticalCount}`] : []),
    ...(warningCount > 0 ? [`경계 ${warningCount}`] : []),
  ]
  const observedText = observedCount > 0 ? ` · 봇 관찰 ${observedCount}` : ''
  const summaryText = categories.length === 0 ? '' : alertParts.length > 0
    ? ` · ${scored.length}개 분석 중 ${alertParts.join(' · ')}${observedText}`
    : ` · ${scored.length}개 분석 · 특이 신호 없음${observedText}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      {/* 갱신 시각 (제목·설명은 앱 머리에 있음) */}
      {data?.generated_at && (
        <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>
            {new Date(data.generated_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
          </span> 갱신{summaryText}
        </div>
      )}

      {/* 카테고리 필터 */}
      <div role="group" aria-label="카테고리" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        {RESEARCH_CATEGORIES.map(cat => {
          const isActive = activeCategory === cat
          const count = cat === '전체' ? categories.length : categories.filter(c => c.name === cat).length
          return (
            <button
              key={cat}
              type="button"
              className="v2-chip"
              aria-pressed={isActive}
              onClick={() => setActiveCategory(cat)}
            >
              {cat} {count > 0 && <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>({count})</span>}
            </button>
          )
        })}
      </div>

      {/* 카드 그리드 */}
      {error && !data ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          {[0, 1, 2, 3].map(i => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-3)' }}>
          {activeCategory === '전체' ? '분석 결과가 없습니다' : `${activeCategory} 분석 결과가 없습니다`}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 36 }}>
          {/* 점수 분석과 봇 관찰을 두 구역으로 나눈 줄 목록 */}
          {[
            { id: 'scored', title: `점수 분석 ${scoredList.length}개`, note: signalTally(toSignalCells(scoredList)), list: scoredList },
            { id: 'observed', title: `봇 관찰 ${observedList.length}개`, note: '점수 없이 봇이 보낸 숫자만 보여 줍니다', list: observedList },
          ].filter(section => section.list.length > 0).map(section => (
            <section key={section.id} aria-labelledby={`research-${section.id}`}>
              <div className="home-sec-head">
                <h2 id={`research-${section.id}`}>{section.title}</h2>
                <span className="research-sec-note">{section.note}</span>
              </div>
              <div className="research-list">
                {section.list.map(cat => (
                  <AnalysisCard
                    key={cat.key}
                    cat={cat}
                    expanded={expandedKey === cat.key}
                    onToggle={() => setExpandedKey(expandedKey === cat.key ? null : cat.key)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
