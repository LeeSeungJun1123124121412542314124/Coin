import { Card } from '../shared/Card'
import type { ReactNode } from 'react'
import { GaugeChart } from '../shared/GaugeChart'
import { GlobalMarketCard } from '../shared/GlobalMarketCard'
import { StockIndexCard } from '../shared/StockIndexCard'
import { StockCard } from '../shared/StockCard'
import { EconomicNewsSection } from '../shared/EconomicNewsSection'
import { AltcoinSeasonCard } from '../shared/AltcoinSeasonCard'
import { MacroHealthCard } from '../shared/MacroHealthCard'
import { StatRow } from '../shared/StatRow'
import { useApi } from '../../hooks/useApi'
import { fmt } from '../../lib/format'

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

function Section({ className, title, children }: { className: string; title: string; children: ReactNode }) {
  return (
    <section className={`mock-card mock-data-section ${className}`}>
      <div className="mock-card-head">
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  )
}

function BtcMarketCard({ btc, kimchi }: { btc?: DashboardData['coins'][number]; kimchi: DashboardData['kimchi'] }) {
  const change = btc?.change_24h ?? null
  const up = change == null || change >= 0

  return (
    <Card className="mock-data-card">
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
    </Card>
  )
}

function CoinCard({ coin }: { coin: DashboardData['coins'][number] }) {
  const change = coin.change_24h ?? null
  const up = change == null || change >= 0

  return (
    <Card className="mock-data-card">
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
    </Card>
  )
}

export function Dashboard() {
  const { data } = useApi<DashboardData>('/api/dashboard', 60_000)
  const { data: stockIndices } = useApi<StockIndexItem[]>('/api/stock-indices', 300_000)
  const { data: krStocks } = useApi<StockItem[]>('/api/stock-prices/kr', 300_000)

  if (!data) return null

  const btc = data.coins?.find(c => c.symbol === 'BTC')
  const mvrv = data.onchain?.mvrv ?? null
  const usMarkets = data.us_market?.filter(m => m.category !== 'korea') ?? []
  const koreaMarkets = data.us_market?.filter(m => m.category === 'korea') ?? []

  return (
    <div className="mock-spf-dashboard mock-real-dashboard">
      <section className="mock-section-title">
        <h1>대시보드</h1>
      </section>

      <div className="mock-real-stack">
        <section className="mock-market-overview">
          <div className="mock-card-head">
            <h2>시장 메인 카드</h2>
          </div>
          <div className="mock-overview-grid">
            <BtcMarketCard btc={btc} kimchi={data.kimchi} />
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
                onOpenModal={() => undefined}
              />
            ))}
            {data.fear_greed && (
              <Card className="mock-data-card mock-gauge-data-card">
                <div className="mock-data-title">공포탐욕지수</div>
                <GaugeChart value={data.fear_greed.value} label={data.fear_greed.label} size={130} />
              </Card>
            )}
            {mvrv !== null && (
              <Card className="mock-data-card mock-gauge-data-card">
                <div className="mock-data-title">MVRV Ratio</div>
                <GaugeChart value={mvrvToGauge(mvrv)} label={mvrvLabel(data.onchain?.mvrv_signal, mvrv)} size={130} />
              </Card>
            )}
          </div>
        </section>

        <section className="mock-news-section">
          <EconomicNewsSection />
        </section>

        <Section className="mock-coin-price-section" title="SPF · 코인 가격">
          <div className="mock-overview-grid mock-compact-grid">
            {data.coins?.map(coin => <CoinCard key={coin.position ?? coin.symbol} coin={coin} />)}
          </div>
        </Section>

        <Section className="mock-kr-stock-section" title="SPF 추이 · 한국 주식">
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
                onOpenModal={() => undefined}
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
    </div>
  )
}
