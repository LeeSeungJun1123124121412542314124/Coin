import { useState } from 'react'
import { AreaChart, Area, Tooltip, ResponsiveContainer, XAxis, YAxis, ReferenceLine } from 'recharts'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../lib/api'
import { Card } from '../shared/Card'
import { StatRow } from '../shared/StatRow'
import { GaugeChart } from '../shared/GaugeChart'
import { CoinSlotEditor } from '../shared/CoinSlotEditor'
import { Modal } from '../shared/Modal'
import { TradingViewChart } from '../shared/TradingViewChart'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { GlobalMarketCard } from '../shared/GlobalMarketCard'
import { fmt } from '../../lib/format'
import { toTvSymbol } from '../../lib/tvSymbolMap'
import { StockIndexCard } from '../shared/StockIndexCard'
import { StockIndexModal } from '../shared/StockIndexModal'
import { StockCard } from '../shared/StockCard'
import { StockSlotEditor } from '../shared/StockSlotEditor'
import { EconomicNewsSection } from '../shared/EconomicNewsSection'
import { AltcoinSeasonCard } from '../shared/AltcoinSeasonCard'
import { KrStockChart } from '../shared/KrStockChart'

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

/** MVRV 값(0~5+)을 게이지(0~100)에 매핑 */
function mvrvToGauge(mvrv: number): number {
  return Math.min(100, Math.round((mvrv / 5) * 100))
}

/** MVRV 신호 → 한글 레이블 */
function mvrvLabel(signal: string | null | undefined, mvrv: number): string {
  if (signal === 'EXTREME_OVERVALUED') return '극단 과평가'
  if (signal === 'OVERVALUED') return '과평가'
  if (signal === 'EXTREME_UNDERVALUED') return '극단 저평가'
  if (signal === 'UNDERVALUED') return '저평가'
  return `정상 (${mvrv.toFixed(2)})`
}

export function Dashboard() {
  const { data, loading, error, refetch, lastUpdated } = useApi<DashboardData>('/api/dashboard', 60_000)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const { data: stockIndices } = useApi<StockIndexItem[]>('/api/stock-indices', 300_000)
  const [activeIndex, setActiveIndex] = useState<{ ticker: string; name: string } | null>(null)

  const { data: krStocks, refetch: refetchKr } = useApi<StockItem[]>('/api/stock-prices/kr', 300_000)
  const { data: usStocks, refetch: refetchUs } = useApi<StockItem[]>('/api/stock-prices/us', 300_000)
  const { data: krSlots, refetch: refetchKrSlots } = useApi<StockSlot[]>('/api/stock-slots/kr', 0)
  const { data: usSlots, refetch: refetchUsSlots } = useApi<StockSlot[]>('/api/stock-slots/us', 0)
  const [activeTvStock, setActiveTvStock] = useState<{ tv_symbol: string; name: string } | null>(null)
  const [activeKrStock, setActiveKrStock] = useState<{ ticker: string; name: string } | null>(null)
  const [editingKr, setEditingKr] = useState(false)
  const [editingUs, setEditingUs] = useState(false)

  // 편집 모드 상태
  const [editMode, setEditMode] = useState(false)
  const [editingPosition, setEditingPosition] = useState<number | null>(null)
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  /** 코인 슬롯 교체 API 호출 */
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
      const msg = err instanceof Error ? err.message : '교체에 실패했습니다'
      setEditError(msg)
    } finally {
      setEditLoading(false)
    }
  }

  if (loading && !data) return <Skeleton />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!data) return null

  const btc = data.coins?.find(c => c.symbol === 'BTC')
  const mvrv = data.onchain?.mvrv ?? null
  const mvrvSignal = data.onchain?.mvrv_signal ?? null

  // 김프 히스토리 — Recharts용 포맷
  const kimchiHistory = (data.kimchi_history ?? []).map(d => ({
    t: d.timestamp.slice(5, 16), // MM-DD HH:mm
    v: d.premium_pct,
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <LastUpdated timestamp={lastUpdated} />

      {/* ── Hero — BTC + 공포탐욕 + MVRV ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
        {/* BTC 카드 + 김프 */}
        <Card onClick={() => setSelectedSymbol('BTC')} style={{ cursor: 'pointer' }}>
          <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: 4 }}>BTC / USDT</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#e2e8f0' }}>
            {btc?.price ? `$${btc.price.toLocaleString()}` : '—'}
          </div>
          <div style={{ color: btc?.change_24h && btc.change_24h >= 0 ? '#4ade80' : '#f87171', fontSize: '0.9rem', marginTop: 4 }}>
            {btc?.change_24h != null ? `${btc.change_24h >= 0 ? '+' : ''}${btc.change_24h.toFixed(2)}%` : '—'}
          </div>
          {data.kimchi && (
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginTop: 8 }}>
              김치프리미엄{' '}
              <span style={{ color: data.kimchi.kimchi_premium_pct >= 0 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                {data.kimchi.kimchi_premium_pct >= 0 ? '+' : ''}{data.kimchi.kimchi_premium_pct.toFixed(2)}%
              </span>
              &nbsp;·&nbsp;환율 ₩{data.kimchi.usd_krw.toLocaleString()}
            </div>
          )}
          {/* 김프 히스토리 미니 차트 */}
          {kimchiHistory.length > 1 && (() => {
            const isPositive = (data.kimchi?.kimchi_premium_pct ?? 0) >= 0
            const chartColor = isPositive ? '#4ade80' : '#f87171'
            return (
              <div style={{ marginTop: 10, height: 64 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={kimchiHistory} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="kimchiGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={chartColor} stopOpacity={0.5} />
                        <stop offset="95%" stopColor={chartColor} stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="t" hide />
                    <YAxis hide domain={['auto', 'auto']} />
                    <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" strokeWidth={1} />
                    <Tooltip
                      contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: '0.7rem' }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(v) => [`${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`, '김프']}
                    />
                    <Area type="monotone" dataKey="v" stroke={chartColor} strokeWidth={2} fill="url(#kimchiGrad)" dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )
          })()}
        </Card>

        {data.global && (
          <GlobalMarketCard data={data.global} />
        )}
        {stockIndices?.map(idx => (
          <StockIndexCard
            key={idx.ticker}
            name={idx.name}
            ticker={idx.ticker}
            price={idx.price}
            change_pct={idx.change_pct}
            sparkline={idx.sparkline ?? []}
            high={idx.high ?? null}
            low={idx.low ?? null}
            onOpenModal={(ticker) => {
              const found = stockIndices.find(i => i.ticker === ticker)
              setActiveIndex(found ? { ticker: found.ticker, name: found.name } : null)
            }}
          />
        ))}

        {/* 공포탐욕 게이지 */}
        {data.fear_greed && (
          <Card>
            <div style={{ color: '#94a3b8', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
              가상자산 공포 및 탐욕 지수
            </div>
            <GaugeChart value={data.fear_greed.value} label={data.fear_greed.label} size={130} />
          </Card>
        )}

        {/* MVRV 게이지 */}
        {mvrv !== null && (
          <Card>
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>MVRV Ratio</div>
            <GaugeChart value={mvrvToGauge(mvrv)} label={mvrvLabel(mvrvSignal, mvrv)} size={130} />
            <div style={{ textAlign: 'center', marginTop: 4, color: '#94a3b8', fontSize: '0.75rem' }}>
              원값: <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{mvrv.toFixed(2)}</span>
            </div>
          </Card>
        )}
      </div>

      {/* ── 경제 뉴스 ── */}
      <EconomicNewsSection />

      {/* ── 코인 카드 섹션 ── */}
      <section>
        {/* 헤더: 제목 + 편집 토글 버튼 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '0 0 10px' }}>
          <h2 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: 0 }}>코인가격</h2>
          <button
            onClick={() => {
              setEditMode(prev => !prev)
              setEditingPosition(null)
              setEditError(null)
            }}
            style={{
              background: editMode ? '#1e3a5f' : 'transparent',
              border: `1px solid ${editMode ? '#60a5fa' : '#475569'}`,
              borderRadius: 4,
              color: editMode ? '#60a5fa' : '#94a3b8',
              cursor: 'pointer',
              fontSize: '0.7rem',
              padding: '2px 8px',
            }}
          >
            {editMode ? '완료' : '편집'}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {data.coins?.map(coin => {
            const isEditing = editMode && editingPosition === coin.position
            return (
              <Card
                key={coin.position ?? coin.symbol}
                onClick={() => {
                  if (editMode) {
                    setEditingPosition(coin.position)
                    setEditError(null)
                  } else {
                    setSelectedSymbol(coin.symbol)
                  }
                }}
                style={{
                  cursor: 'pointer',
                  transition: 'border-color 0.15s',
                  position: 'relative',
                  ...(editMode && { borderColor: '#f59e0b' }),
                }}
                className={editMode ? '' : 'coin-card'}
              >
                {isEditing ? (
                  <CoinSlotEditor
                    position={coin.position}
                    currentSymbol={coin.symbol}
                    onSave={(query) => handleSlotSave(coin.position, query)}
                    onCancel={() => { setEditingPosition(null); setEditError(null) }}
                    loading={editLoading}
                    error={editError}
                  />
                ) : (
                  <>
                    {editMode && (
                      <span style={{ position: 'absolute', top: 6, right: 8, fontSize: '0.7rem', color: '#f59e0b', pointerEvents: 'none' }}>✏️</span>
                    )}
                    <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>{coin.symbol}</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#e2e8f0', margin: '4px 0' }}>
                      {coin.price ? `$${coin.price.toLocaleString()}` : '—'}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: (coin.change_24h ?? 0) >= 0 ? '#4ade80' : '#f87171' }}>
                      {coin.change_24h != null ? `${coin.change_24h >= 0 ? '+' : ''}${coin.change_24h.toFixed(2)}%` : '—'}
                    </div>
                    {(coin.high_24h != null || coin.low_24h != null) && (
                      <div style={{ display: 'flex', gap: 8, marginTop: 4, fontSize: '0.7rem' }}>
                        {coin.high_24h != null && (
                          <span><span style={{ color: '#f87171' }}>H </span><span style={{ color: '#94a3b8' }}>${coin.high_24h.toLocaleString()}</span></span>
                        )}
                        {coin.low_24h != null && (
                          <span><span style={{ color: '#4ade80' }}>L </span><span style={{ color: '#94a3b8' }}>${coin.low_24h.toLocaleString()}</span></span>
                        )}
                      </div>
                    )}
                  </>
                )}
              </Card>
            )
          })}
        </div>
      </section>

      {/* ── 알트코인 시즌 지수 ── */}
      {data.altcoin_season && (
        <section>
          <AltcoinSeasonCard {...data.altcoin_season} />
        </section>
      )}

      {/* ── 한국주식 섹션 ── */}
      <section>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '0 0 10px' }}>
          <h2 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: 0 }}>한국주식</h2>
          <button
            onClick={() => setEditingKr(prev => !prev)}
            style={{
              background: editingKr ? '#1e3a5f' : 'transparent',
              border: `1px solid ${editingKr ? '#60a5fa' : '#475569'}`,
              borderRadius: 4,
              color: editingKr ? '#60a5fa' : '#94a3b8',
              cursor: 'pointer',
              fontSize: '0.7rem',
              padding: '2px 8px',
            }}
          >
            {editingKr ? '완료' : '편집'}
          </button>
        </div>
        {editingKr && krSlots && (
          <StockSlotEditor
            market="kr"
            slots={krSlots}
            onUpdate={() => { refetchKr(); refetchKrSlots() }}
          />
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {krStocks?.map(s => (
            <StockCard
              key={s.ticker}
              ticker={s.ticker}
              name={s.name}
              tv_symbol={s.tv_symbol}
              price={s.price}
              change_pct={s.change_pct}
              sparkline={s.sparkline ?? []}
              high={s.high}
              low={s.low}
              onOpenModal={(_, name) => setActiveKrStock({ ticker: s.ticker, name })}
            />
          ))}
        </div>
      </section>

      {/* ── 미국주식 섹션 ── */}
      <section>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '0 0 10px' }}>
          <h2 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: 0 }}>미국주식</h2>
          <button
            onClick={() => setEditingUs(prev => !prev)}
            style={{
              background: editingUs ? '#1e3a5f' : 'transparent',
              border: `1px solid ${editingUs ? '#60a5fa' : '#475569'}`,
              borderRadius: 4,
              color: editingUs ? '#60a5fa' : '#94a3b8',
              cursor: 'pointer',
              fontSize: '0.7rem',
              padding: '2px 8px',
            }}
          >
            {editingUs ? '완료' : '편집'}
          </button>
        </div>
        {editingUs && usSlots && (
          <StockSlotEditor
            market="us"
            slots={usSlots}
            onUpdate={() => { refetchUs(); refetchUsSlots() }}
          />
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {usStocks?.map(s => (
            <StockCard
              key={s.ticker}
              ticker={s.ticker}
              name={s.name}
              tv_symbol={s.tv_symbol}
              price={s.price}
              change_pct={s.change_pct}
              sparkline={s.sparkline ?? []}
              high={s.high}
              low={s.low}
              onOpenModal={(sym, name) => setActiveTvStock({ tv_symbol: sym, name })}
            />
          ))}
        </div>
      </section>

      {/* ── 미국 시장 + 파생상품 ── */}
      <div className="grid-2" style={{ gap: 16 }}>
        {/* 미국 시장 */}
        <Card>
          <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>미국 시장</h3>
          {data.us_market?.map((m, i, arr) => {
            const isFirstKorea = m.category === 'korea' && (i === 0 || arr[i - 1].category !== 'korea')
            const isNotFirst = i > 0 && !isFirstKorea
            return (
              <div key={m.name}>
                {isFirstKorea && (
                  <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '14px 0 10px', paddingTop: 14, borderTop: '1px solid #1e293b' }}>한국 시장</h3>
                )}
                {isNotFirst && (
                  <div style={{ borderTop: '1px solid #2d3f55', margin: '0' }} />
                )}
                <StatRow label={m.name} value={fmt(m.price, 2)} change={m.change_pct} />
              </div>
            )
          }) ?? <div style={{ color: '#64748b' }}>데이터 없음</div>}
        </Card>

        {/* 파생상품 + 온체인 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card>
            <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>파생상품</h3>
            <StatRow label="미결제약정 (OI)" value={fmt(data.derivatives.open_interest?.open_interest)} />
            {data.derivatives.oi_change && (
              <>
                <div style={{ borderTop: '1px solid #2d3f55' }} />
                <StatRow
                  label="OI 변화 (1h)"
                  value={data.derivatives.oi_change.change_1h_pct != null
                    ? `${data.derivatives.oi_change.change_1h_pct >= 0 ? '+' : ''}${data.derivatives.oi_change.change_1h_pct.toFixed(2)}%`
                    : '—'}
                  highlight={
                    (data.derivatives.oi_change.change_1h_pct ?? 0) > 3 ? 'up'
                    : (data.derivatives.oi_change.change_1h_pct ?? 0) < -3 ? 'down'
                    : 'neutral'
                  }
                />
                <StatRow
                  label="OI 변화 (24h)"
                  value={data.derivatives.oi_change.change_24h_pct != null
                    ? `${data.derivatives.oi_change.change_24h_pct >= 0 ? '+' : ''}${data.derivatives.oi_change.change_24h_pct.toFixed(2)}%`
                    : '—'}
                  highlight={
                    (data.derivatives.oi_change.change_24h_pct ?? 0) > 5 ? 'up'
                    : (data.derivatives.oi_change.change_24h_pct ?? 0) < -5 ? 'down'
                    : 'neutral'
                  }
                />
              </>
            )}
            <div style={{ borderTop: '1px solid #2d3f55' }} />
            <StatRow
              label="펀딩레이트"
              value={`${data.derivatives.funding_rate?.funding_rate_pct?.toFixed(4) ?? '—'}%`}
              highlight={
                (data.derivatives.funding_rate?.funding_rate_pct ?? 0) > 0.03 ? 'down'
                : (data.derivatives.funding_rate?.funding_rate_pct ?? 0) < -0.01 ? 'up'
                : 'neutral'
              }
            />
            {data.derivatives.long_short && (
              <>
                <div style={{ borderTop: '1px solid #2d3f55' }} />
                <StatRow
                  label="롱/숏 비율"
                  value={`${(data.derivatives.long_short.long_account * 100).toFixed(1)}% / ${(data.derivatives.long_short.short_account * 100).toFixed(1)}%`}
                />
              </>
            )}
          </Card>

          <Card>
            <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>온체인 (BTC)</h3>
            {data.onchain ? (
              <>
                <StatRow label="거래소 유입" value={`${data.onchain.exchange_inflow.toFixed(0)} BTC`} highlight="down" />
                <div style={{ borderTop: '1px solid #2d3f55' }} />
                <StatRow label="거래소 유출" value={`${data.onchain.exchange_outflow.toFixed(0)} BTC`} highlight="up" />
              </>
            ) : (
              <div style={{ color: '#64748b', fontSize: '0.8rem' }}>데이터 없음</div>
            )}
            {data.coinbase_btc && btc?.price && (
              <>
                <div style={{ borderTop: '1px solid #2d3f55' }} />
                <StatRow
                  label="코인베이스 프리미엄"
                  value={`${((data.coinbase_btc / btc.price - 1) * 100).toFixed(3)}%`}
                  highlight={(data.coinbase_btc / btc.price - 1) > 0 ? 'up' : 'down'}
                />
              </>
            )}
          </Card>
        </div>
      </div>

      {/* ── 시장 유동성 (스테이블코인) + 해시레이트 ── */}
      {(data.stablecoins || data.hashrate) && (
        <div className="grid-2" style={{ gap: 16 }}>
          {/* 스테이블코인 시가총액 */}
          {data.stablecoins && data.stablecoins.length > 0 && (
            <Card>
              <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>
                시장 유동성
              </h3>
              {data.stablecoins.map((sc, i) => (
                <div key={sc.symbol}>
                  {i > 0 && <div style={{ borderTop: '1px solid #2d3f55' }} />}
                  <StatRow
                    label={`${sc.symbol} 시총`}
                    value={sc.market_cap ? `$${(sc.market_cap / 1e9).toFixed(1)}B` : '—'}
                    change={sc.change_24h}
                  />
                </div>
              ))}
            </Card>
          )}

          {/* BTC 해시레이트 */}
          {data.hashrate && (
            <Card>
              <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>
                BTC 네트워크
              </h3>
              <StatRow
                label="해시레이트"
                value={`${data.hashrate.hashrate_eh.toFixed(0)} EH/s`}
                highlight="neutral"
              />
            </Card>
          )}
        </div>
      )}
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

      {/* 주식 종목 TradingView 모달 */}
      <Modal open={!!activeTvStock} onClose={() => setActiveTvStock(null)}>
        {activeTvStock && <TradingViewChart symbol={activeTvStock.tv_symbol} />}
      </Modal>

      {/* 한국 주식 Recharts 차트 모달 */}
      <Modal open={!!activeKrStock} onClose={() => setActiveKrStock(null)}>
        {activeKrStock && <KrStockChart ticker={activeKrStock.ticker} name={activeKrStock.name} />}
      </Modal>

      {/* 지수 차트 모달 */}
      <StockIndexModal
        ticker={activeIndex?.ticker ?? null}
        name={activeIndex?.name ?? ''}
        onClose={() => setActiveIndex(null)}
      />

      <style>{`.coin-card:hover { border-color: #60a5fa !important; } .stock-card:hover { border-color: #60a5fa !important; }`}</style>
    </div>
  )
}
