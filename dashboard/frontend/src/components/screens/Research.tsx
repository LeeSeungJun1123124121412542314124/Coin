import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import ErrorState from '../shared/ErrorState'
import LastUpdated from '../shared/LastUpdated'
import { LEVEL_COLORS, LEVEL_BG, LEVEL_BORDER } from '../../lib/theme'
import { ScoreBar } from '../shared/ScoreBar'

interface CategoryAnalysis {
  key: string
  name: string
  level: string
  score: number
  title: string
  summary: string
  details: Record<string, unknown>
  updated_at: string
}

interface SignalItem {
  id: string
  name: string
  status: 'green' | 'yellow' | 'red'
  label: string
  note: string
}

interface ResearchData {
  generated_at: string
  categories: CategoryAnalysis[]
}

const CATEGORY_COLORS: Record<string, string> = {
  '매크로': '#60a5fa',
  '온체인': '#4ade80',
  '파생상품': '#f97316',
  '알트코인': '#a78bfa',
  '기술적분석': '#f59e0b',
  '시장분석': '#f87171',
  '기타': '#94a3b8',
}


const LEVEL_LABELS: Record<string, string> = {
  critical: '위험',
  warning:  '경계',
  bearish:  '약세',
  bullish:  '강세',
  neutral:  '중립',
}

const LEVEL_ICONS: Record<string, string> = {
  critical: '🚨',
  warning:  '⚠️',
  bearish:  '🔵',
  bullish:  '🟢',
  neutral:  '⚪',
}

const CATEGORIES = ['전체', '매크로', '온체인', '파생상품', '알트코인', '기술적분석', '시장분석', '기타']


function AnalysisCard({ cat, expanded, onToggle }: {
  cat: CategoryAnalysis
  expanded: boolean
  onToggle: () => void
}) {
  const catColor = CATEGORY_COLORS[cat.name] ?? '#94a3b8'
  const levelColor = LEVEL_COLORS[cat.level] ?? '#94a3b8'
  const levelBg = LEVEL_BG[cat.level] ?? 'rgba(100,116,139,0.08)'
  const levelBorder = LEVEL_BORDER[cat.level] ?? 'rgba(100,116,139,0.2)'
  const levelLabel = LEVEL_LABELS[cat.level] ?? cat.level
  const icon = LEVEL_ICONS[cat.level] ?? '⚪'
  const time = cat.updated_at ? new Date(cat.updated_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : ''

  const details = cat.details as Record<string, unknown>

  return (
    <div
      style={{
        background: expanded ? levelBg : '#111827',
        border: `1px solid ${expanded ? levelBorder : '#1e293b'}`,
        borderRadius: 12,
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
            background: catColor + '22',
            color: catColor,
            border: `1px solid ${catColor}44`,
            borderRadius: 6,
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 600,
          }}>{cat.name}</span>
          <span style={{
            background: levelBg,
            color: levelColor,
            border: `1px solid ${levelColor}44`,
            borderRadius: 6,
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 600,
          }}>{icon} {levelLabel}</span>
        </div>
        <span style={{ fontSize: 11, color: '#475569' }}>{time}</span>
      </div>

      {/* 제목 */}
      <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 8, lineHeight: 1.4 }}>
        {cat.title}
      </div>

      {/* 요약 */}
      <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, marginBottom: 10 }}>
        {cat.summary}
      </div>

      {/* 점수 바 */}
      <ScoreBar score={cat.score} level={cat.level} />

      {/* 상세 정보 (expanded) */}
      {expanded && Object.keys(details).length > 0 && (
        <div style={{
          marginTop: 14,
          paddingTop: 14,
          borderTop: '1px solid #1e293b',
        }}>
          {_renderDetails(cat.key, details)}
        </div>
      )}

      <div style={{ marginTop: 8, textAlign: 'right', fontSize: 11, color: '#334155' }}>
        {expanded ? '▲ 접기' : '▼ 상세'}
      </div>
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
            <span style={{ color: '#64748b' }}>{label}: </span>
            <span style={{ color: '#cbd5e1', fontWeight: 600 }}>{value}</span>
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
              <span style={{ color: '#94a3b8' }}>{c.symbol} </span>
              <span style={{ color: c.change_24h >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                {c.change_24h >= 0 ? '+' : ''}{c.change_24h?.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
        {details.btc_dominance != null && (
          <div style={{ fontSize: 12, color: '#64748b' }}>
            BTC 도미넌스: <span style={{ color: '#cbd5e1' }}>{String(details.btc_dominance)}%</span>
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
            <span style={{ color: '#64748b' }}>{label}: </span>
            <span style={{ color: '#cbd5e1', fontWeight: 600 }}>{value}</span>
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
      return <div style={{ fontSize: 12, color: '#64748b' }}>국채 경매 일정 없음 또는 수집 중</div>
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>향후 국채 경매 (일부)</div>
        {auctions.slice(0, 8).map((a, i) => (
          <div key={i} style={{ fontSize: 12, color: '#94a3b8' }}>
            <span style={{ color: '#cbd5e1' }}>{a.auction_date?.slice(0, 10)}</span>
            {' · '}{a.type} {a.term}
            {a.offering_amount_b != null && (
              <span style={{ color: '#64748b' }}> · {a.offering_amount_b}B$</span>
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
          <div key={i} style={{ fontSize: 12, color: '#94a3b8' }}>
            <span style={{ color: LEVEL_COLORS[ins.level] ?? '#94a3b8', fontWeight: 600 }}>
              {ins.title}
            </span>
            {' — '}{ins.body}
          </div>
        ))}
      </div>
    )
  }

  if (key === 'samsung_signals') {
    const signals = (details.signals as SignalItem[]) ?? []
    const peakCount = (details.peak_count as number) ?? 0
    const total = (details.total as number) ?? 0

    const statusColorMap: Record<string, string> = {
      green: '#22c55e',
      yellow: '#f59e0b',
      red: '#ef4444',
    }

    return (
      <div>
        {peakCount >= 1 && (
          <div style={{ fontSize: 11, color: '#f59e0b', marginBottom: 10, fontWeight: 600 }}>
            ⚠️ {peakCount}/{total} 모니터링
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {signals.map((signal) => {
            const statusColor = statusColorMap[signal.status] ?? '#94a3b8'
            return (
              <div key={signal.id} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 10, color: statusColor }}>●</span>
                    <span style={{ fontSize: 12, color: '#cbd5e1' }}>{signal.name}</span>
                  </div>
                  <span style={{ fontSize: 11, color: statusColor, fontWeight: 600 }}>{signal.label}</span>
                </div>
                {signal.note && (
                  <div style={{ fontSize: 11, color: '#64748b', marginLeft: 16, marginTop: 2 }}>
                    {signal.note}
                  </div>
                )}
              </div>
            )
          })}
        </div>
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
            <span style={{ color: '#64748b' }}>{k}: </span>
            <span style={{ color: '#cbd5e1', fontWeight: 600 }}>{String(v)}</span>
          </div>
        ))}
    </div>
  )
}

function SkeletonCard() {
  return (
    <div style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12, padding: '18px 20px' }}>
      {[80, 140, 100, 20].map((w, i) => (
        <div key={i} style={{
          height: i === 0 ? 16 : i === 1 ? 14 : i === 2 ? 12 : 6,
          width: `${w}%`,
          background: '#1e293b',
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

  const { data, loading, error, refetch, lastUpdated } = useApi<ResearchData>('/api/research-analysis', 120_000)

  const categories = data?.categories ?? []
  const filtered = activeCategory === '전체'
    ? categories
    : categories.filter(c => c.name === activeCategory)

  return (
    <div style={{ padding: '20px 16px', maxWidth: 1200, margin: '0 auto' }}>
      <LastUpdated timestamp={lastUpdated} />
      {/* 헤더 */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: '#f1f5f9', margin: 0 }}>리서치</h2>
        <p style={{ fontSize: 13, color: '#64748b', margin: '4px 0 0' }}>
          수집된 데이터 기반 카테고리별 자동 분석
          {data?.generated_at && (
            <span style={{ marginLeft: 8 }}>
              • {new Date(data.generated_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })} 갱신
            </span>
          )}
        </p>
      </div>

      {/* 카테고리 필터 */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        {CATEGORIES.map(cat => {
          const isActive = activeCategory === cat
          const catColor = cat === '전체' ? '#60a5fa' : (CATEGORY_COLORS[cat] ?? '#94a3b8')
          const count = cat === '전체' ? categories.length : categories.filter(c => c.name === cat).length
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              style={{
                background: isActive ? catColor + '22' : 'transparent',
                border: `1px solid ${isActive ? catColor : '#334155'}`,
                borderRadius: 8,
                padding: '5px 12px',
                fontSize: 12,
                color: isActive ? catColor : '#64748b',
                cursor: 'pointer',
                transition: 'all 0.15s',
                fontWeight: isActive ? 600 : 400,
              }}
            >
              {cat} {count > 0 && <span style={{ opacity: 0.7 }}>({count})</span>}
            </button>
          )
        })}
      </div>

      {/* 카드 그리드 */}
      {error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          {[0, 1, 2, 3].map(i => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#475569' }}>
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
