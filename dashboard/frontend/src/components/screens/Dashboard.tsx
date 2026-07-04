import { useState, type ReactNode } from 'react'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '../shared/Card'
import { GaugeChart } from '../shared/GaugeChart'
import { GlobalMarketCard } from '../shared/GlobalMarketCard'
import { StockIndexCard } from '../shared/StockIndexCard'
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
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../lib/api'
import { fmt } from '../../lib/format'
import { toTvSymbol } from '../../lib/tvSymbolMap'

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

function mvrvToGauge(mvrv: number): number {
  return Math.min(100, Math.round((mvrv / 5) * 100))
}

function mvrvLabel(signal: string | null | undefined, mvrv: number): string {
  if (signal === 'EXTREME_OVERVALUED') return '극단 과평가'
  if (signal === 'OVERVALUED') return '과평가'
  if (signal === 'EXTREME_UNDERVALUED') return '극단 저평가'
  if (signal === 'UNDERVALUED') return '저평가'
  return `정상 (${mvrv.toFixed(2)})`
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

function BtcMarketCard({
  btc,
  kimchi,
  kimchiHistory,
  onOpen,
}: {
  btc?: DashboardData['coins'][number]
  kimchi: DashboardData['kimchi']
  kimchiHistory: Array<{ t: string; v: number }>
  onOpen: () => void
}) {
  const change = btc?.change_24h ?? null
  const up = change == null || change >= 0
  const chartColor = (kimchi?.kimchi_premium_pct ?? 0) >= 0 ? '#4ade80' : '#f87171'

  return (
    <Card className="mock-data-card" onClick={onOpen} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column' }}>
      <div className="mock-data-title">BTC / USDT</div>
      <div className="mock-data-value">{btc?.price ? `$${btc.price.toLocaleString()}` : '-'}</div>
      <div className={up ? 'mock-up' : 'mock-down'}>
        {change != null ? `${up ? '+' : ''}${change.toFixed(2)}%` : '-'}
      </div>
      {kimchi && (
        <div className="mock-data-meta">
          김치프리미엄 <b className={kimchi.kimchi_premium_pct >= 0 ? 'mock-up' : 'mock-down'}>
            {kimchi.kimchi_premium_pct >= 0 ? '+' : ''}{kimchi.kimchi_premium_pct.toFixed(2)}%
          </b>
          <span>환율 {kimchi.usd_krw.toLocaleString()}</span>
        </div>
      )}
      {kimchiHistory.length > 1 && (
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
              <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" strokeWidth={1} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: '0.7rem' }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v) => [`${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`, '김프']}
              />
              <Area type="monotone" dataKey="v" stroke={chartColor} strokeWidth={2} fill="url(#mockKimchiGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function CoinCard({
  coin,
  editMode,
  isEditing,
  loading,
  error,
  onEdit,
  onOpen,
  onSave,
  onCancel,
}: {
  coin: DashboardData['coins'][number]
  editMode: boolean
  isEditing: boolean
  loading: boolean
  error: string | null
  onEdit: () => void
  onOpen: () => void
  onSave: (query: string) => void
  onCancel: () => void
}) {
  const change = coin.change_24h ?? null
  const up = change == null || change >= 0

  return (
    <Card
      className={`mock-data-card${editMode ? '' : ' coin-card'}`}
      onClick={editMode ? onEdit : onOpen}
      style={{ cursor: 'pointer', position: 'relative' }}
    >
      {isEditing ? (
        <CoinSlotEditor
          position={coin.position}
          currentSymbol={coin.symbol}
          onSave={onSave}
          onCancel={onCancel}
          loading={loading}
          error={error}
        />
      ) : (
        <>
      {editMode && <span className="mock-card-edit-mark">✎</span>}
      <div className="mock-data-title">{coin.symbol}</div>
      <div className="mock-data-value">{coin.price ? `$${coin.price.toLocaleString()}` : '-'}</div>
      <div className={up ? 'mock-up' : 'mock-down'}>
        {change != null ? `${up ? '+' : ''}${change.toFixed(2)}%` : '-'}
      </div>
      {(coin.high_24h != null || coin.low_24h != null) && (
        <div className="mock-data-meta">
          {coin.high_24h != null && <span>H ${coin.high_24h.toLocaleString()}</span>}
          {coin.low_24h != null && <span>L ${coin.low_24h.toLocaleString()}</span>}
        </div>
      )}
        </>
      )}
    </Card>
  )
}

export function Dashboard() {
  const { data, refetch } = useApi<DashboardData>('/api/dashboard', 60_000)
  const { data: stockIndices } = useApi<StockIndexItem[]>('/api/stock-indices', 300_000)
  const { data: krStocks, refetch: refetchKr } = useApi<StockItem[]>('/api/stock-prices/kr', 300_000)
  const { data: krSlots, refetch: refetchKrSlots } = useApi<StockSlot[]>('/api/stock-slots/kr', 0)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [activeIndex, setActiveIndex] = useState<{ ticker: string; name: string } | null>(null)
  const [activeKrStock, setActiveKrStock] = useState<{ ticker: string; name: string } | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [editingPosition, setEditingPosition] = useState<number | null>(null)
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
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

  if (!data) return null

  const btc = data.coins?.find(c => c.symbol === 'BTC')
  const mvrv = data.onchain?.mvrv ?? null
  const usMarkets = data.us_market?.filter(m => m.category !== 'korea') ?? []
  const koreaMarkets = data.us_market?.filter(m => m.category === 'korea') ?? []
  const kimchiHistory = (data.kimchi_history ?? []).map(d => ({
    t: d.timestamp.slice(5, 16),
    v: d.premium_pct,
  }))

  return (
    <div className="mock-spf-dashboard mock-real-dashboard">
      <div className="mock-real-stack">
        <section className="mock-market-overview">
          <div className="mock-card-head">
            <h2>시장 메인 카드</h2>
          </div>
          <div className="mock-overview-grid">
            <BtcMarketCard btc={btc} kimchi={data.kimchi} kimchiHistory={kimchiHistory} onOpen={() => setSelectedSymbol('BTC')} />
            {data.global && <GlobalMarketCard data={data.global} />}
            {stockIndices?.slice(0, 3).map(idx => (
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
                  const found = stockIndices.find(item => item.ticker === ticker)
                  setActiveIndex(found ? { ticker: found.ticker, name: found.name } : null)
                }}
              />
            ))}
            {data.fear_greed && (
              <Card className="mock-data-card mock-gauge-data-card">
                <div className="mock-data-title">공포탐욕지수</div>
                <GaugeChart value={data.fear_greed.value} label={data.fear_greed.label} size={110} />
              </Card>
            )}
            {mvrv !== null && (
              <Card className="mock-data-card mock-gauge-data-card">
                <div className="mock-data-title">MVRV Ratio</div>
                <GaugeChart value={mvrvToGauge(mvrv)} label={mvrvLabel(data.onchain?.mvrv_signal, mvrv)} size={110} />
              </Card>
            )}
          </div>
        </section>

        <section className="mock-news-section">
          <EconomicNewsSection />
        </section>

        <Section
          className="mock-coin-price-section"
          title="코인가격"
          actions={(
            <button
              type="button"
              onClick={() => {
                setEditMode(prev => !prev)
                setEditingPosition(null)
                setEditError(null)
              }}
            >
              {editMode ? '완료' : '편집'}
            </button>
          )}
        >
          <div className="mock-overview-grid mock-compact-grid">
            {data.coins?.map(coin => (
              <CoinCard
                key={coin.position ?? coin.symbol}
                coin={coin}
                editMode={editMode}
                isEditing={editMode && editingPosition === coin.position}
                loading={editLoading}
                error={editError}
                onEdit={() => {
                  setEditingPosition(coin.position)
                  setEditError(null)
                }}
                onOpen={() => setSelectedSymbol(coin.symbol)}
                onSave={(query) => handleSlotSave(coin.position, query)}
                onCancel={() => {
                  setEditingPosition(null)
                  setEditError(null)
                }}
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
                <StatRow key={market.name} label={market.name} value={market.price.toLocaleString()} change={market.change_pct} />
              ))}
            </Card>
            <Card>
              <h3 className="mock-detail-title">한국시장</h3>
              {koreaMarkets.map(market => (
                <StatRow key={market.name} label={market.name} value={market.price.toLocaleString()} change={market.change_pct} />
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
                  highlight={(data.coinbase_btc / btc.price - 1) > 0 ? 'up' : 'down'}
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
