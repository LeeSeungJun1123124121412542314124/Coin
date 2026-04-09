import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import { StatRow } from '../shared/StatRow'
import { GaugeChart } from '../shared/GaugeChart'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { fmt } from '../../lib/format'

interface DashboardData {
  coins: Array<{
    symbol: string
    price: number | null
    change_24h: number | null
    market_cap: number | null
  }>
  global: {
    total_market_cap_usd: number | null
    btc_dominance: number | null
    market_cap_change_24h: number | null
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
  }
  coinbase_btc: number | null
  kimchi: { kimchi_premium_pct: number; usd_krw: number } | null
  fear_greed: { value: number; label: string } | null
  onchain: {
    exchange_inflow: number
    exchange_outflow: number
  } | null
}


export function Dashboard() {
  const { data, loading, error, refetch, lastUpdated } = useApi<DashboardData>('/api/dashboard', 60_000)

  if (loading && !data) return <Skeleton />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!data) return null

  const btc = data.coins?.find(c => c.symbol === 'BTC')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <LastUpdated timestamp={lastUpdated} />
      {/* Hero — BTC + 공포탐욕 */}
      <div className="grid-hero" style={{ gap: 16 }}>
        <Card>
          <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: 4 }}>BTC / USDT</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#e2e8f0' }}>
            {btc?.price ? `$${btc.price.toLocaleString()}` : '—'}
          </div>
          <div style={{ color: btc?.change_24h && btc.change_24h >= 0 ? '#4ade80' : '#f87171', fontSize: '0.9rem', marginTop: 4 }}>
            {btc?.change_24h != null ? `${btc.change_24h >= 0 ? '+' : ''}${btc.change_24h.toFixed(2)}%` : '—'}
          </div>
          {data.kimchi && (
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginTop: 8 }}>
              김치프리미엄 <span style={{ color: data.kimchi.kimchi_premium_pct >= 0 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                {data.kimchi.kimchi_premium_pct >= 0 ? '+' : ''}{data.kimchi.kimchi_premium_pct.toFixed(2)}%
              </span>
              &nbsp;·&nbsp;환율 ₩{data.kimchi.usd_krw.toLocaleString()}
            </div>
          )}
        </Card>
        {data.fear_greed && (
          <Card>
            <GaugeChart value={data.fear_greed.value} label={data.fear_greed.label} size={130} />
          </Card>
        )}
      </div>

      {/* 코인 카드 6개 */}
      <section>
        <h2 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>코인 가격</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {data.coins?.map(coin => (
            <Card key={coin.symbol}>
              <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>{coin.symbol}</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#e2e8f0', margin: '4px 0' }}>
                {coin.price ? `$${coin.price.toLocaleString()}` : '—'}
              </div>
              <div style={{ fontSize: '0.8rem', color: (coin.change_24h ?? 0) >= 0 ? '#4ade80' : '#f87171' }}>
                {coin.change_24h != null ? `${coin.change_24h >= 0 ? '+' : ''}${coin.change_24h.toFixed(2)}%` : '—'}
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* 미국 시장 + 파생상품 */}
      <div className="grid-2" style={{ gap: 16 }}>
        {/* 미국 시장 */}
        <Card>
          <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>미국 시장</h3>
          {data.us_market?.map(m => (
            <StatRow key={m.name} label={m.name} value={fmt(m.price, 2)} change={m.change_pct} />
          )) ?? <div style={{ color: '#64748b' }}>데이터 없음</div>}
        </Card>

        {/* 파생상품 + 온체인 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card>
            <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>파생상품</h3>
            <StatRow label="미결제약정 (OI)" value={fmt(data.derivatives.open_interest?.open_interest)} />
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
              <StatRow
                label="롱/숏 비율"
                value={`${(data.derivatives.long_short.long_account * 100).toFixed(1)}% / ${(data.derivatives.long_short.short_account * 100).toFixed(1)}%`}
              />
            )}
          </Card>

          <Card>
            <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>온체인 (BTC)</h3>
            {data.onchain ? (
              <>
                <StatRow label="거래소 유입" value={`${data.onchain.exchange_inflow.toFixed(0)} BTC`} highlight="down" />
                <StatRow label="거래소 유출" value={`${data.onchain.exchange_outflow.toFixed(0)} BTC`} highlight="up" />
              </>
            ) : (
              <div style={{ color: '#64748b', fontSize: '0.8rem' }}>데이터 없음</div>
            )}
            {data.global && (
              <>
                <StatRow label="BTC 도미넌스" value={`${data.global.btc_dominance?.toFixed(1) ?? '—'}%`} />
                <StatRow label="전체 시총" value={fmt(data.global.total_market_cap_usd)} change={data.global.market_cap_change_24h} />
              </>
            )}
            {data.coinbase_btc && btc?.price && (
              <StatRow
                label="코인베이스 프리미엄"
                value={`${((data.coinbase_btc / btc.price - 1) * 100).toFixed(3)}%`}
                highlight={(data.coinbase_btc / btc.price - 1) > 0 ? 'up' : 'down'}
              />
            )}
          </Card>
        </div>
      </div>

    </div>
  )
}

