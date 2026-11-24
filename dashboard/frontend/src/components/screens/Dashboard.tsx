import { useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '../shared/Card'
import { StockIndexModal } from '../shared/StockIndexModal'
import { StockCard } from '../shared/StockCard'
import { CoinSlotEditor } from '../shared/CoinSlotEditor'
import { StockSlotEditor } from '../shared/StockSlotEditor'
import { Modal } from '../shared/Modal'
import { TradingViewChart } from '../shared/TradingViewChart'
import { KrStockChart } from '../shared/KrStockChart'
import { EconomicNewsSection } from '../shared/EconomicNewsSection'
import { AltcoinSeasonCard } from '../shared/AltcoinSeasonCard'
import { MacroHealthCard } from '../shared/MacroHealthCard'
import { StatRow } from '../shared/StatRow'
import Skeleton, { SkeletonCard } from '../shared/Skeleton'
import ErrorState from '../shared/ErrorState'
import LastUpdated from '../shared/LastUpdated'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../lib/api'
import { fmt, fmtCoinPrice, fmtFixed, fmtIndex, fmtSignedPct } from '../../lib/format'
import { toTvSymbol } from '../../lib/tvSymbolMap'
import { C, changeArrow, changeColor, softBg } from '../../lib/theme'
import type { ChartResponse } from '../../lib/learningApi'
import { summarizeBtcPhase, type BtcPhase, type PhaseTone } from './dashboardPhase'
import { summarizeMood, type Mood } from './dashboardMood'
import { BotNews, BtcLadder, DiffList, SignalBoard } from './HomeBrief'
import { ladderPosition, signalTally, splitMoodSentence, toBotNews, toDiffRows, toSignalCells, type BriefCategory } from './homeBriefView'

interface DashboardData {
  coins: Array<{
    position: number
    symbol: string
    price: number | null
    change_24h: number | null
    market_cap: number | null
    tv_symbol: string | null
    high_24h: number | null
    low_24h: number | null
  }>
  global: {
    total_market_cap_usd: number | null
    btc_dominance: number | null
    eth_dominance: number | null
    market_cap_change_24h: number | null
    market_cap_chart: Array<{ t: number; v: number }> | null
  } | null
  us_market: Array<{
    name: string
    category: string
    price: number
    change_pct: number
  }> | null
  derivatives: {
    open_interest: { open_interest: number } | null
    funding_rate: { funding_rate_pct: number } | null
    long_short: { long_short_ratio: number; long_account: number; short_account: number } | null
    oi_change: { change_1h_pct: number | null; change_24h_pct: number | null } | null
  }
  coinbase_btc: number | null
  kimchi: { kimchi_premium_pct: number; usd_krw: number } | null
  kimchi_history: Array<{ timestamp: string; premium_pct: number }> | null
  fear_greed: { value: number; label: string } | null
  onchain: {
    exchange_inflow: number
    exchange_outflow: number
    mvrv: number | null
    mvrv_signal: string | null
  } | null
  stablecoins: Array<{ symbol: string; market_cap: number | null; change_24h: number | null }> | null
  hashrate: { hashrate_eh: number } | null
  altcoin_season: {
    index_value: number
    season_label: 'altcoin_season' | 'neutral' | 'bitcoin_season'
    history: Array<{ date: string; value: number; market_cap: number }>
    cached_at: string
    is_stale: boolean
    yesterday_value: number | null
    last_week_value: number | null
    last_month_value: number | null
    yearly_high: { value: number; date: string; season_label: string } | null
    yearly_low: { value: number; date: string; season_label: string } | null
  } | null
}

interface StockIndexItem {
  ticker: string
  name: string
  price: number | null
  change_pct: number | null
  sparkline: number[]
  high: number | null
  low: number | null
}

interface StockSlot {
  position: number
  ticker: string
  name: string
  tv_symbol: string | null
}

interface StockItem {
  ticker: string
  name: string
  tv_symbol: string | null
  price: number | null
  change_pct: number | null
  sparkline: number[]
  high: number | null
  low: number | null
}

// 분위기 카드에 쓰는 두 API의 필요한 부분만
interface SpfApi {
  today_prediction: { direction: string; confidence: number } | null
}

interface MarketApi {
  insights: Array<{ level: string; title: string }>
}

// MVRV 신호 → 해석 라벨·색 (신호값이 없으면 정상)
function mvrvNote(signal: string | null | undefined): { text: string; color: string } {
  if (signal === 'EXTREME_OVERVALUED') return { text: '극단 과평가', color: 'var(--danger)' }
  if (signal === 'OVERVALUED') return { text: '과평가', color: 'var(--warn)' }
  if (signal === 'EXTREME_UNDERVALUED') return { text: '극단 저평가', color: 'var(--ok)' }
  if (signal === 'UNDERVALUED') return { text: '저평가', color: 'var(--ok)' }
  return { text: '정상', color: 'var(--ok)' }
}

// 가격 띠의 한 칸
interface StripCell {
  key: string
  group: 'coin' | 'index'
  name: string
  price: string
  change: number | null
  onClick?: () => void
}

function Section({ className, title, actions, children }: { className: string; title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className={`mock-card mock-data-section ${className}`}>
      <div className="mock-card-head">
        <h2>{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  )
}

const TONE_COLOR: Record<PhaseTone, string> = { up: 'var(--up)', down: 'var(--down)', flat: 'var(--text-2)' }
const TONE_MARK: Record<PhaseTone, string> = { up: '▲', down: '▼', flat: '–' }
const fmtUsdt = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 })

// BTC 시장 국면 — 학습 탭 일봉 차트(BTCUSDT) 요약을 받아 그린다(차트 조회는 Dashboard에서 한 번만). 404·오류·빈 응답은 안내 문구
function BtcPhaseCard({ phase, loading }: { phase: BtcPhase | null; loading: boolean }) {
  // 한 번이라도 응답(성공·실패)을 받았으면 폴링 재요청 중에는 Skeleton을 다시 띄우지 않는다
  const [settled, setSettled] = useState(false)
  if (!loading && !settled) setSettled(true)
  if (loading && !phase && !settled) return <SkeletonCard height={260} />

  return (
    <Card className="phase-card">
      <div className="phase-head">
        <div>
          <h2 className="phase-title">BTC 시장 국면</h2>
          <span className="phase-pill">일봉 · 바이낸스 현물</span>
        </div>
        <Link to="/learning" className="phase-link">{phase ? '학습 탭에서 차트 보기 →' : '학습 탭으로 이동 →'}</Link>
      </div>
      {phase ? (
        <>
          <div className="phase-price-row">
            <span className="phase-price">{fmtUsdt(phase.close)}</span>
            <span className="phase-unit">USDT</span>
          </div>
          <div className="phase-sub">
            <span style={{ color: changeColor(phase.changePct), fontWeight: 600 }}>
              {changeArrow(phase.changePct)} {Math.abs(phase.changePct).toFixed(2)}%
            </span>
            <span style={{ marginLeft: 6 }}>전일 대비</span>
            <span className="phase-range">90일 범위 {fmtUsdt(phase.low)} – {fmtUsdt(phase.high)}</span>
          </div>
          <svg className="phase-spark" viewBox="0 0 300 64" preserveAspectRatio="none" aria-hidden="true">
            <polygon points={`${phase.spark} 300,64 0,64`} fill={softBg(C.accent, 0.14)} />
            <polyline points={phase.spark} fill="none" stroke={C.accent} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="phase-states">
            {phase.states.map(s => (
              <div key={s.k} className="phase-state">
                <div className="phase-state-label">{s.k}</div>
                <div className="phase-state-value" style={{ color: TONE_COLOR[s.tone] }}>{TONE_MARK[s.tone]} {s.v}</div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="phase-empty">학습 탭에서 BTCUSDT를 추가하면 표시됩니다</div>
      )}
    </Card>
  )
}

// 오늘의 판단: 분위기 한 줄을 큰 제목으로 + 근거 줄 (근거마다 해당 화면으로 이동)
const BASIS_LINK: Record<string, string> = { phase: '/learning', spf: '/spf', warnings: '/market', fearGreed: '/market' }

function MoodCard({ mood, failedBasis }: { mood: Mood; failedBasis: string[] }) {
  const { headline, tail } = splitMoodSentence(mood.sentence)
  const today = new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })
  return (
    <section className="dash-mood" aria-labelledby="mood-title">
      <div className="dash-mood-head">
        <span className="home-kicker">오늘의 판단 · {today}</span>
        <span className="dash-mood-badge" data-tone={mood.ready ? mood.tone : 'wait'}>{mood.badge}</span>
      </div>
      <h1 id="mood-title" className="home-headline">{headline}</h1>
      {(tail || (mood.ready && mood.tally)) && (
        <p className="home-lede">
          {tail}
          {mood.ready && mood.tally && <span className="dash-mood-tally">근거 {mood.basis.length}개 중 {mood.tally}</span>}
        </p>
      )}
      <div className="dash-basis-grid">
        {mood.basis.map(b => (
          <Link key={b.key} to={BASIS_LINK[b.key]} className="dash-basis">
            <span className="dash-basis-label">{b.label}</span>
            <span className="dash-basis-tag" data-vote={b.vote}>{b.tag}</span>
            <span className="dash-basis-value">{b.value}</span>
          </Link>
        ))}
      </div>
      {failedBasis.length > 0 && <p className="dash-mood-fail">일부 근거를 불러오지 못했습니다: {failedBasis.join(' / ')}</p>}
    </section>
  )
}

export function Dashboard() {
  const { data, error, refetch, lastUpdated } = useApi<DashboardData>('/api/dashboard', 60_000)
  const { data: stockIndices } = useApi<StockIndexItem[]>('/api/stock-indices', 300_000)
  const { data: usStocks, refetch: refetchUs } = useApi<StockItem[]>('/api/stock-prices/us', 300_000)
  const { data: usSlots, refetch: refetchUsSlots } = useApi<StockSlot[]>('/api/stock-slots/us', 0)
  const { data: krStocks, refetch: refetchKr } = useApi<StockItem[]>('/api/stock-prices/kr', 300_000)
  const { data: krSlots, refetch: refetchKrSlots } = useApi<StockSlot[]>('/api/stock-slots/kr', 0)
  // 학습 일봉 차트는 여기서 한 번만 조회해 분위기 카드와 국면 카드가 같이 쓴다
  const { data: chart, loading: chartLoading, error: chartError } = useApi<ChartResponse>('/api/learning/chart?symbol=BTCUSDT&interval=1d&limit=90', 300_000)
  const { data: spf, error: spfError } = useApi<SpfApi>('/api/spf-data', 300_000)
  // 인사이트만 돌려주는 경량 엔드포인트(market-analysis와 같은 generate_insights 결과)
  const { data: market, error: marketError } = useApi<MarketApi>('/api/insights', 300_000)
  // 신호판·달라진 것·봇 소식은 리서치 분석 결과로 그린다
  const { data: research, loading: researchLoading } = useApi<{ categories: BriefCategory[] }>('/api/research-analysis', 600_000)
  const [priceTab, setPriceTab] = useState<'coin' | 'index'>('coin')
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [activeIndex, setActiveIndex] = useState<{ ticker: string; name: string } | null>(null)
  const [activeTvStock, setActiveTvStock] = useState<{ tv_symbol: string; name: string } | null>(null)
  const [activeKrStock, setActiveKrStock] = useState<{ ticker: string; name: string } | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [editingPosition, setEditingPosition] = useState<number | null>(null)
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editingUs, setEditingUs] = useState(false)
  const [editingKr, setEditingKr] = useState(false)

  const handleSlotSave = async (position: number, query: string) => {
    setEditLoading(true)
    setEditError(null)
    try {
      await apiFetch(`/api/coin-slots/${position}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      })
      await refetch()
      setEditingPosition(null)
      setEditMode(false)
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : '교체에 실패했습니다')
    } finally {
      setEditLoading(false)
    }
  }

  // 첫 로딩은 뼈대, 첫 로딩 실패는 오류와 다시 시도 — 빈 화면으로 두지 않는다
  if (error && !data) return <ErrorState error={error} onRetry={refetch} />
  if (!data) return <Skeleton />

  const btc = data.coins?.find(c => c.symbol === 'BTC')
  const mvrv = data.onchain?.mvrv ?? null
  const chartColor = changeColor(data.kimchi?.kimchi_premium_pct)
  const phase = summarizeBtcPhase(chart)
  const warnings = market ? market.insights.filter(i => i.level === 'warning' || i.level === 'critical') : null
  const moodBase = summarizeMood({
    phaseTones: phase ? phase.states.map(st => st.tone) : null,
    phaseValue: phase?.states.slice(0, 2).map(st => st.v).join(' · '),
    spf: spf ? { direction: spf.today_prediction?.direction ?? '', confidence: spf.today_prediction?.confidence ?? 0 } : null,
    warningCount: warnings ? warnings.length : null,
    warningTitles: warnings?.map(w => w.title),
    fearGreed: data.fear_greed?.value ?? null,
    fearGreedLabel: data.fear_greed?.label,
  })
  // 조회에 실패했고 근거 데이터가 없는 항목 — 판정 규칙은 건드리지 않고 화면에서만 알린다
  const failedBasis = [
    ...(chartError && !chart ? ['BTC 국면'] : []),
    ...(spfError && !spf ? ['SPF 전망'] : []),
    ...(marketError && !market ? ['주의 신호'] : []),
  ]
  const basisPending = (!chart && !chartError) || (!spf && !spfError) || (!market && !marketError)
  const mood: Mood = !moodBase.ready && failedBasis.length > 0 && !basisPending
    ? { ...moodBase, sentence: '근거를 충분히 받지 못했습니다' }
    : moodBase

  // 가격 띠: 코인 슬롯 전부 + 지수 3개 + 원/달러. 편집 중에는 코인 칸이 슬롯 편집을 연다
  const cells: StripCell[] = [
    ...(data.coins ?? []).map((coin): StripCell => ({
      key: `coin-${coin.position ?? coin.symbol}`,
      group: 'coin',
      name: coin.symbol,
      price: fmtCoinPrice(coin.price),
      change: coin.change_24h ?? null,
      onClick: editMode
        ? () => { setEditingPosition(coin.position); setEditError(null) }
        : () => setSelectedSymbol(coin.symbol),
    })),
    ...(stockIndices ?? []).slice(0, 3).map((idx): StripCell => ({
      key: `idx-${idx.ticker}`,
      group: 'index',
      name: idx.name,
      price: fmtIndex(idx.price),
      change: idx.change_pct,
      onClick: () => setActiveIndex({ ticker: idx.ticker, name: idx.name }),
    })),
    ...(data.kimchi ? [{ key: 'usdkrw', group: 'index', name: '원/달러', price: fmtFixed(data.kimchi.usd_krw, 2), change: null } satisfies StripCell] : []),
  ]
  const editingCoin = editMode ? data.coins?.find(c => c.position === editingPosition) : undefined

  const briefCategories = research?.categories ?? []
  const signalCells = toSignalCells(briefCategories)
  const heatmapLevels = briefCategories.find(c => c.key === 'bot_heatmap')?.details.levels

  // 핵심 지표: 해석(note)은 기존 라벨·신호값만 쓰고, 없는 항목은 비워 둔다
  const pct = (v: number | null | undefined, digits: number) => (v == null ? '—' : `${fmtFixed(v, digits)}%`)
  const changeNote = (v: number | null | undefined) => ({
    text: v == null ? '' : `${changeArrow(v)} ${fmtFixed(Math.abs(v), 2)}%`,
    color: changeColor(v),
  })
  const oiChange = data.derivatives.oi_change?.change_24h_pct
  const mcapChange = changeNote(data.global?.market_cap_change_24h)
  const kpis: Array<{ label: string; value: string; note: string; color: string }> = [
    ...(data.fear_greed ? [{
      label: '공포탐욕', value: String(data.fear_greed.value), note: data.fear_greed.label,
      color: data.fear_greed.value <= 25 ? 'var(--danger)' : data.fear_greed.value >= 75 ? 'var(--warn)' : 'var(--text-2)',
    }] : []),
    ...(mvrv !== null ? [{ label: 'MVRV', value: fmtFixed(mvrv, 2), note: mvrvNote(data.onchain?.mvrv_signal).text, color: mvrvNote(data.onchain?.mvrv_signal).color }] : []),
    ...(data.kimchi ? [{ label: '김치프리미엄', value: fmtSignedPct(data.kimchi.kimchi_premium_pct), note: '', color: 'var(--text-2)' }] : []),
    { label: '펀딩비', value: pct(data.derivatives.funding_rate?.funding_rate_pct, 4), note: '', color: 'var(--text-2)' },
    {
      label: '미결제약정', value: fmt(data.derivatives.open_interest?.open_interest),
      note: oiChange != null ? `24h ${changeNote(oiChange).text}` : '', color: changeColor(oiChange),
    },
    ...(data.global ? [
      { label: 'BTC 도미넌스', value: pct(data.global.btc_dominance, 1), note: '', color: 'var(--text-2)' },
      { label: '암호화폐 시총', value: fmt(data.global.total_market_cap_usd), note: mcapChange.text, color: mcapChange.color },
    ] : []),
  ]

  const usMarkets = data.us_market?.filter(m => m.category !== 'korea') ?? []
  const koreaMarkets = data.us_market?.filter(m => m.category === 'korea') ?? []
  const kimchiHistory = (data.kimchi_history ?? []).map(d => ({
    t: d.timestamp.slice(5, 16),
    v: d.premium_pct,
  }))

  return (
    <div className="mock-spf-dashboard mock-real-dashboard">
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      <div className="mock-real-stack">
        <div className="home-hero">
          <div className="home-hero-main">
            <MoodCard mood={mood} failedBasis={failedBasis} />
            <SignalBoard cells={signalCells} tally={signalTally(signalCells)} loading={researchLoading} />
          </div>
          <div className="home-side">
            <BtcLadder price={btc?.price ?? null} change={btc?.change_24h ?? null} ladder={ladderPosition(heatmapLevels, btc?.price)} />
          </div>
        </div>

        <div className="home-cols">
          <DiffList rows={toDiffRows(briefCategories, 4)} loading={researchLoading} />
          <BotNews items={toBotNews(briefCategories)} />
        </div>

        <section className="dash-card dash-strip mock-coin-price-section" aria-label="가격" data-tab={priceTab}>
          <div className="dash-strip-head">
            <h2>가격</h2>
            <div className="v2-seg" role="group" aria-label="가격 묶음">
              <button type="button" className="v2-seg-btn" aria-pressed={priceTab === 'coin'} onClick={() => setPriceTab('coin')}>코인</button>
              <button type="button" className="v2-seg-btn" aria-pressed={priceTab === 'index'} onClick={() => setPriceTab('index')}>지수</button>
            </div>
            <button
              type="button"
              className="dash-strip-edit"
              onClick={() => {
                // 편집할 코인 칸은 코인 탭에만 보이므로 편집을 켜면 코인 탭으로 돌린다
                if (!editMode) setPriceTab('coin')
                setEditMode(prev => !prev)
                setEditingPosition(null)
                setEditError(null)
              }}
            >
              {editMode ? '완료' : '편집'}
            </button>
          </div>
          <div
            className="dash-strip-grid"
            style={{ '--dash-cols': cells.length, '--dash-cols-half': Math.ceil(cells.length / 2) } as CSSProperties}
          >
            {cells.map(cell => {
              const body = (
                <>
                  <span className="dash-cell-name">{cell.name}</span>
                  <span className="dash-cell-price">{cell.price}</span>
                  <span className="dash-cell-change" style={{ color: changeColor(cell.change) }}>
                    {cell.change == null ? '—' : `${changeArrow(cell.change)} ${fmtFixed(Math.abs(cell.change), 2)}%`}
                  </span>
                </>
              )
              return cell.onClick ? (
                <button key={cell.key} type="button" className="dash-cell" data-group={cell.group} data-edit={editMode && cell.group === 'coin' ? 'true' : undefined} onClick={cell.onClick}>{body}</button>
              ) : (
                <div key={cell.key} className="dash-cell" data-group={cell.group}>{body}</div>
              )
            })}
          </div>
          {editingCoin && (
            <div className="dash-strip-editor">
              <CoinSlotEditor
                position={editingCoin.position}
                currentSymbol={editingCoin.symbol}
                onSave={(query) => handleSlotSave(editingCoin.position, query)}
                onCancel={() => {
                  setEditingPosition(null)
                  setEditError(null)
                }}
                loading={editLoading}
                error={editError}
              />
            </div>
          )}
        </section>

        <div className="dash-top">
          <BtcPhaseCard phase={phase} loading={chartLoading} />
          <Card className="dash-kpi-card">
            <h2 className="dash-card-title">핵심 지표</h2>
            <div className="v2-list">
              {kpis.map(k => (
                <div key={k.label} className="v2-row">
                  <span>{k.label}</span>
                  <span className="dash-kpi-val">
                    {k.note && <span className="v2-note" style={{ color: k.color }}>{k.note}</span>}
                    <span>{k.value}</span>
                  </span>
                </div>
              ))}
            </div>
            {kimchiHistory.length > 1 && (
              <>
                <div className="dash-kimchi-caption">김치프리미엄 추이</div>
                <div className="mock-kimchi-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={kimchiHistory} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                      <defs>
                        <linearGradient id="mockKimchiGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={chartColor} stopOpacity={0.5} />
                          <stop offset="95%" stopColor={chartColor} stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="t" hide />
                      <YAxis hide domain={['auto', 'auto']} />
                      <ReferenceLine y={0} stroke={C.text3} strokeDasharray="3 3" strokeWidth={1} />
                      <Tooltip
                        contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, fontSize: '12px' }}
                        labelStyle={{ color: C.text2 }}
                        formatter={(v) => [fmtSignedPct(Number(v)), '김프']}
                      />
                      <Area type="monotone" dataKey="v" stroke={chartColor} strokeWidth={2} fill="url(#mockKimchiGrad)" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </Card>
        </div>

        <section className="mock-news-section">
          <EconomicNewsSection />
        </section>

        <Section
          className="mock-us-stock-section"
          title="미국주식"
          actions={(
            <button type="button" onClick={() => setEditingUs(prev => !prev)}>
              {editingUs ? '완료' : '편집'}
            </button>
          )}
        >
          {editingUs && usSlots && (
            <StockSlotEditor
              market="us"
              slots={usSlots}
              onUpdate={() => {
                refetchUs()
                refetchUsSlots()
              }}
            />
          )}
          <div className="mock-overview-grid mock-compact-grid">
            {usStocks?.map(stock => (
              <StockCard
                key={stock.ticker}
                ticker={stock.ticker}
                name={stock.name}
                tv_symbol={stock.tv_symbol}
                price={stock.price}
                change_pct={stock.change_pct}
                sparkline={stock.sparkline ?? []}
                high={stock.high}
                low={stock.low}
                onOpenModal={(tvSymbol, name) => setActiveTvStock({ tv_symbol: tvSymbol, name })}
              />
            ))}
          </div>
        </Section>

        <Section
          className="mock-kr-stock-section"
          title="한국주식"
          actions={(
            <button type="button" onClick={() => setEditingKr(prev => !prev)}>
              {editingKr ? '완료' : '편집'}
            </button>
          )}
        >
          {editingKr && krSlots && (
            <StockSlotEditor
              market="kr"
              slots={krSlots}
              onUpdate={() => {
                refetchKr()
                refetchKrSlots()
              }}
            />
          )}
          <div className="mock-overview-grid mock-compact-grid">
            {krStocks?.map(stock => (
              <StockCard
                key={stock.ticker}
                ticker={stock.ticker}
                name={stock.name}
                tv_symbol={stock.tv_symbol}
                price={stock.price}
                change_pct={stock.change_pct}
                sparkline={stock.sparkline ?? []}
                high={stock.high}
                low={stock.low}
                onOpenModal={(_, name) => setActiveKrStock({ ticker: stock.ticker, name })}
              />
            ))}
          </div>
        </Section>

        {data.altcoin_season && (
          <section className="mock-altcoin-season-section">
            <AltcoinSeasonCard {...data.altcoin_season} />
          </section>
        )}

        <section className="mock-market-detail-section">
          <div className="mock-detail-grid">
            <Card>
              <h3 className="mock-detail-title">미국시장</h3>
              {usMarkets.map(market => (
                <StatRow key={market.name} label={market.name} value={fmtIndex(market.price)} change={market.change_pct} />
              ))}
            </Card>
            <Card>
              <h3 className="mock-detail-title">한국시장</h3>
              {koreaMarkets.map(market => (
                <StatRow key={market.name} label={market.name} value={fmtIndex(market.price)} change={market.change_pct} />
              ))}
            </Card>
            <Card>
              <h3 className="mock-detail-title">파생상품</h3>
              <StatRow label="미결제약정(OI)" value={fmt(data.derivatives.open_interest?.open_interest)} />
              <StatRow label="OI 변화(1h)" value={data.derivatives.oi_change?.change_1h_pct != null ? `${data.derivatives.oi_change.change_1h_pct.toFixed(2)}%` : '-'} />
              <StatRow label="펀딩레이트" value={`${data.derivatives.funding_rate?.funding_rate_pct?.toFixed(4) ?? '-'}%`} />
              {data.derivatives.long_short && (
                <StatRow label="롱/숏 비율" value={`${(data.derivatives.long_short.long_account * 100).toFixed(1)}% / ${(data.derivatives.long_short.short_account * 100).toFixed(1)}%`} />
              )}
            </Card>
            <Card>
              <h3 className="mock-detail-title">온체인</h3>
              {data.onchain ? (
                <>
                  <StatRow label="거래소 유입" value={`${data.onchain.exchange_inflow.toFixed(0)} BTC`} highlight="down" />
                  <StatRow label="거래소 유출" value={`${data.onchain.exchange_outflow.toFixed(0)} BTC`} highlight="up" />
                </>
              ) : (
                <div className="mock-empty">데이터 없음</div>
              )}
              {data.coinbase_btc && btc?.price && (
                <StatRow
                  label="코인베이스 프리미엄"
                  value={`${((data.coinbase_btc / btc.price - 1) * 100).toFixed(3)}%`}
                  highlight={data.coinbase_btc === btc.price ? 'neutral' : data.coinbase_btc > btc.price ? 'up' : 'down'}
                />
              )}
            </Card>
            <Card>
              <h3 className="mock-detail-title">시장유동성</h3>
              {data.stablecoins?.map(sc => (
                <StatRow key={sc.symbol} label={`${sc.symbol} 시총`} value={sc.market_cap ? `$${(sc.market_cap / 1e9).toFixed(1)}B` : '-'} change={sc.change_24h} />
              ))}
            </Card>
            <Card>
              <h3 className="mock-detail-title">BTC 네트워크</h3>
              <StatRow label="해시레이트" value={data.hashrate ? `${data.hashrate.hashrate_eh.toFixed(0)} EH/s` : '-'} />
            </Card>
          </div>
        </section>

        <section>
          <MacroHealthCard />
        </section>
      </div>
      <Modal open={!!selectedSymbol} onClose={() => setSelectedSymbol(null)}>
        {selectedSymbol && (
          <TradingViewChart
            symbol={toTvSymbol(
              selectedSymbol,
              data.coins?.find(c => c.symbol === selectedSymbol)?.tv_symbol
            )}
          />
        )}
      </Modal>
      <Modal open={!!activeTvStock} onClose={() => setActiveTvStock(null)}>
        {activeTvStock && <TradingViewChart symbol={activeTvStock.tv_symbol} />}
      </Modal>
      <Modal open={!!activeKrStock} onClose={() => setActiveKrStock(null)}>
        {activeKrStock && <KrStockChart ticker={activeKrStock.ticker} name={activeKrStock.name} />}
      </Modal>
      <StockIndexModal
        ticker={activeIndex?.ticker ?? null}
        name={activeIndex?.name ?? ''}
        onClose={() => setActiveIndex(null)}
      />
    </div>
  )
}
