import { useState } from 'react'
import { AreaChart, Area, Tooltip, ResponsiveContainer, XAxis } from 'recharts'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import { StatRow } from '../shared/StatRow'
import { GaugeChart } from '../shared/GaugeChart'
import { Modal } from '../shared/Modal'
import { TradingViewChart } from '../shared/TradingViewChart'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { fmt } from '../../lib/format'
import { toTvSymbol } from '../../lib/tvSymbolMap'

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
          {kimchiHistory.length > 1 && (
            <div style={{ marginTop: 10, height: 48 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={kimchiHistory} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="kimchiGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="t" hide />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: '0.7rem' }}
                    labelStyle={{ color: '#94a3b8' }}
                    formatter={(v) => [`${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`, '김프']}
                  />
                  <Area type="monotone" dataKey="v" stroke="#60a5fa" strokeWidth={1.5} fill="url(#kimchiGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* 공포탐욕 게이지 */}
        {data.fear_greed && (
          <Card>
            <GaugeChart value={data.fear_greed.value} label={data.fear_greed.label} size={130} />
          </Card>
        )}

        {/* MVRV 게이지 */}
        {mvrv !== null && (
          <Card>
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>MVRV Ratio</div>
            <GaugeChart
              value={mvrvToGauge(mvrv)}
              label={mvrvLabel(mvrvSignal, mvrv)}
              size={130}
            />
            <div style={{ textAlign: 'center', marginTop: 4, color: '#94a3b8', fontSize: '0.75rem' }}>
              원값: <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{mvrv.toFixed(2)}</span>
            </div>
          </Card>
        )}
      </div>

      {/* ── 코인 카드 6개 ── */}
      <section>
        <h2 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>코인 가격</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {data.coins?.map(coin => (
            <Card
              key={coin.symbol}
              onClick={() => setSelectedSymbol(coin.symbol)}
              style={{ cursor: 'pointer', transition: 'border-color 0.15s' }}
              className="coin-card"
            >
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

      {/* ── 미국 시장 + 파생상품 ── */}
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
            {/* OI 변화율 */}
            {data.derivatives.oi_change && (
              <>
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

      {/* ── 시장 유동성 (스테이블코인) + 해시레이트 ── */}
      {(data.stablecoins || data.hashrate) && (
        <div className="grid-2" style={{ gap: 16 }}>
          {/* 스테이블코인 시가총액 */}
          {data.stablecoins && data.stablecoins.length > 0 && (
            <Card>
              <h3 style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px' }}>
                시장 유동성
              </h3>
              {data.stablecoins.map(sc => (
                <StatRow
                  key={sc.symbol}
                  label={`${sc.symbol} 시총`}
                  value={sc.market_cap ? `$${(sc.market_cap / 1e9).toFixed(1)}B` : '—'}
                  change={sc.change_24h}
                />
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
        {selectedSymbol && <TradingViewChart symbol={toTvSymbol(selectedSymbol)} />}
      </Modal>

      <style>{`.coin-card:hover { border-color: #60a5fa !important; }`}</style>
    </div>
  )
}
