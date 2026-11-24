import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import ErrorState from '../shared/ErrorState'
import LastUpdated from '../shared/LastUpdated'
import { C, LEVEL_COLORS, LEVEL_BG, LEVEL_BORDER, changeArrow, changeColor, softBg } from '../../lib/theme'
import { ScoreBar } from '../shared/ScoreBar'
import {
  RESEARCH_CATEGORIES,
  RESEARCH_CATEGORY_COLORS,
  STOCK_SENTIMENT_INDEX_NOTES,
  sortByUrgency,
  toCompareLines,
  toKrStockFlowDetailRows,
  toStockSentimentDetailRows,
} from './researchView'
import type { CategoryCompare } from './researchView'

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
}

interface SignalItem {
  id: string
  name: string
  status: 'green' | 'yellow' | 'red'
  label: string
  note?: string
}

interface SignalSection {
  key: string
  name: string
  signals: SignalItem[]
}

interface ResearchData {
  generated_at: string
  categories: CategoryAnalysis[]
}

const LEVEL_LABELS: Record<string, string> = {
  critical: '위험',
  warning:  '경계',
  bearish:  '약세',
  bullish:  '강세',
  neutral:  '중립',
}

const LEVEL_ICONS: Record<string, string> = {
  critical: '!',
  warning:  '!',
  bearish:  '▼',
  bullish:  '▲',
  neutral:  '●',
}

const STATUS_COLORS: Record<string, string> = {
  green: C.ok,
  yellow: C.warn,
  red: C.danger,
}


function AnalysisCard({ cat, expanded, onToggle }: {
  cat: CategoryAnalysis
  expanded: boolean
  onToggle: () => void
}) {
  const catColor = RESEARCH_CATEGORY_COLORS[cat.name] ?? C.text2
  const levelColor = LEVEL_COLORS[cat.level] ?? C.text2
  const levelBg = LEVEL_BG[cat.level] ?? softBg(C.text2, 0.08)
  const levelBorder = LEVEL_BORDER[cat.level] ?? softBg(C.text2, 0.2)
  const levelLabel = LEVEL_LABELS[cat.level] ?? cat.level
  const icon = LEVEL_ICONS[cat.level] ?? '●'
  const time = cat.updated_at ? new Date(cat.updated_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : ''

  const details = cat.details as Record<string, unknown>
  const compareLines = toCompareLines(cat, LEVEL_LABELS)

  return (
    <div
      style={{
        background: expanded ? levelBg : 'var(--surface)',
        border: `1px solid ${expanded ? levelBorder : 'var(--border)'}`,
        boxShadow: 'var(--shadow-card)',
        borderRadius: 16,
        padding: '18px 20px',
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
      onClick={onToggle}
    >
      {/* 헤더 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span style={{
            background: softBg(catColor, 0.14),
            color: catColor,
            border: `1px solid ${softBg(catColor, 0.28)}`,
            borderRadius: 6,
            padding: '2px 8px',
            fontSize: 12,
            fontWeight: 600,
          }}>{cat.name}</span>
          <span style={{
            background: levelBg,
            color: levelColor,
            border: `1px solid ${softBg(levelColor, 0.28)}`,
            borderRadius: 6,
            padding: '2px 8px',
            fontSize: 12,
            fontWeight: 600,
          }}>{icon} {levelLabel}</span>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{time}</span>
      </div>

      {/* 제목 */}
      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 8, lineHeight: 1.4 }}>
        {cat.title}
      </div>

      {/* 어제·7일 전 대비 — 이전 저장분이 있을 때만 */}
      {(compareLines.prevLine || compareLines.weekLine) && (
        <div style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 8 }}>
          {compareLines.prevLine && <div style={{ color: 'var(--text-2)' }}>{compareLines.prevLine}</div>}
          {compareLines.weekLine && <div style={{ color: 'var(--text-3)' }}>{compareLines.weekLine}</div>}
        </div>
      )}

      {/* 요약 — 이전 저장분이 있으면 오늘·이전 요약을 나란히 */}
      <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 10 }}>
        {compareLines.prevSummary ? (
          <>
            <div><span style={{ color: 'var(--text-3)' }}>오늘: </span>{cat.summary}</div>
            <div style={{ color: 'var(--text-3)' }}>{compareLines.prevSummary.label}: {compareLines.prevSummary.text}</div>
          </>
        ) : cat.summary}
      </div>

      {/* 점수 바 */}
      <ScoreBar score={cat.score} level={cat.level} />

      {/* 상세 정보 (expanded) */}
      {expanded && Object.keys(details).length > 0 && (
        <div style={{
          marginTop: 14,
          paddingTop: 14,
          borderTop: '1px solid var(--line)',
        }}>
          {_renderDetails(cat.key, details)}
        </div>
      )}

      {/* 클릭은 카드의 onClick이 받는다 — 키보드·보조기기용 버튼 */}
      <button type="button" aria-expanded={expanded} className="research-detail-btn">
        {expanded ? '▲ 접기' : '▼ 상세'}
      </button>
    </div>
  )
}

function _renderDetails(key: string, details: Record<string, unknown>) {
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

  if (key === 'whale') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {[
          ['롱', `${details.long_count}명 (${details.long_pct}%)`],
          ['숏', `${details.short_count}명 (${details.short_pct}%)`],
          ['중립', `${details.neutral_count}명`],
          ['합계', `${details.total}명`],
        ].map(([label, value]) => (
          <div key={label as string} style={{ fontSize: 12 }}>
            <span style={{ color: 'var(--text-3)' }}>{label}: </span>
            <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{value}</span>
          </div>
        ))}
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

  if (key === 'semiconductor_signals') {
    const sections = (details.sections as SignalSection[]) ?? []
    const peakCount = (details.peak_count as number) ?? 0
    const total = (details.total as number) ?? 0
    const asOf = details.as_of as string | undefined
    const daysSince = details.days_since as number | undefined

    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          {peakCount >= 1 ? (
            <span style={{ fontSize: 12, color: 'var(--warn-text)', fontWeight: 600 }}>! 정점 임박 {peakCount}/{total}</span>
          ) : <span />}
          {asOf && (
            <span style={{ fontSize: 12, color: typeof daysSince === 'number' && daysSince > 21 ? 'var(--warn-text)' : 'var(--text-3)' }}>
              최종 확인: {asOf}{typeof daysSince === 'number' ? ` (${daysSince}일 전)` : ''}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {sections.map((section) => (
            <div key={section.key}>
              <div style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 700, marginBottom: 6 }}>{section.name}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {section.signals.map((signal) => {
                  const statusColor = STATUS_COLORS[signal.status] ?? C.text2
                  return (
                    <div key={signal.id}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontSize: 12, color: statusColor }}>●</span>
                          <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{signal.name}</span>
                        </div>
                        <span style={{ fontSize: 12, color: statusColor, fontWeight: 600 }}>{signal.label}</span>
                      </div>
                      {signal.note && (
                        <div style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 16, marginTop: 2 }}>
                          {signal.note}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
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
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-card)', borderRadius: 16, padding: '18px 20px' }}>
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
  const criticalCount = categories.filter(c => c.level === 'critical').length
  const warningCount = categories.filter(c => c.level === 'warning').length
  const alertParts = [
    ...(criticalCount > 0 ? [`위험 ${criticalCount}`] : []),
    ...(warningCount > 0 ? [`경계 ${warningCount}`] : []),
  ]
  const summaryText = categories.length === 0 ? '' : alertParts.length > 0
    ? ` · ${categories.length}개 분석 중 ${alertParts.join(' · ')}`
    : ` · ${categories.length}개 분석 · 특이 신호 없음`

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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          {filtered.map(cat => (
            <AnalysisCard
              key={cat.key}
              cat={cat}
              expanded={expandedKey === cat.key}
              onToggle={() => setExpandedKey(expandedKey === cat.key ? null : cat.key)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
