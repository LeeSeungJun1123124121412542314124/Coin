import { useState } from 'react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { fmt } from '../../lib/format'
import { C, changeColor, changeArrow, softBg } from '../../lib/theme'
import { AssetTabs } from '../shared/AssetTabs'
import { readAssetTab, replaceAssetTab, type AssetTab } from '../shared/assetTabUtils'

interface Position {
  coin: string
  side: 'long' | 'short'
  size: number
  entry_px: number | null
  unrealized_pnl: number | null
  leverage: number | null
}

interface Whale {
  rank: number
  address: string
  display_name: string | null
  account_value: number | null
  pnl_30d: number | null
  roi_30d: number | null
  volume_30d: number | null
  unrealized_pnl: number | null
  positions: Position[]
  btc_position: Position | null
}

interface WhaleData {
  whales: Whale[]
  total: number
}

interface Consensus {
  long_count: number
  short_count: number
  neutral_count: number
  total: number
  consensus: string
  long_pct: number
  short_pct: number
}

interface KrInvestorFlowRecord {
  date: string
  foreign_net: number
  institution_net: number
  individual_net: number
}

interface KrInvestorFlowData {
  market: 'KOSPI' | 'KOSDAQ'
  stale: boolean
  records: KrInvestorFlowRecord[]
}

type KrMarket = 'KOSPI' | 'KOSDAQ'

interface UsInsiderSummary {
  ticker: string
  name: string
  buy_value: number
  sell_value: number
  net_value: number
  trade_count: number
}

interface UsInsiderTrade {
  ticker: string
  transaction_date: string
  filed_at: string
  insider_name: string
  insider_title: string | null
  code: 'P' | 'S'
  shares: number | null
  price: number | null
  value: number | null
}

interface UsInsiderData {
  summaries: UsInsiderSummary[]
  trades: UsInsiderTrade[]
}

interface Us13fSummary {
  ticker: string
  latest_quarter: string | null
  latest_value: number
  prev_value: number
  qoq_change: number | null
}

interface Us13fHolding {
  accession_no: string
  seq: number
  institution: string
  ticker: string
  quarter: string
  shares: number | null
  value_usd: number | null
  put_call: 'Call' | null
}

interface Us13fData {
  quarters: string[]
  holdings: Us13fHolding[]
  summaries: Us13fSummary[]
}

function BtcBadge({ pos }: { pos: Position | null }) {
  if (!pos) return <span style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>—</span>
  const color = pos.side === 'long' ? 'var(--up)' : 'var(--down)'
  const label = pos.side === 'long' ? '롱' : '숏'
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 6, fontSize: '0.72rem', fontWeight: 600,
      background: softBg(pos.side === 'long' ? C.up : C.down, 0.14),
      color,
    }}>
      BTC {label}
      {pos.leverage != null && ` ${pos.leverage.toFixed(0)}x`}
    </span>
  )
}

function PositionList({ positions }: { positions: Position[] }) {
  if (!positions || positions.length === 0) {
    return <span style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>포지션 없음</span>
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {positions.slice(0, 5).map((p, i) => (
        <span key={i} style={{
          padding: '1px 7px', borderRadius: 5, fontSize: '0.7rem',
          background: softBg(p.side === 'long' ? C.up : C.down, 0.12),
          color: p.side === 'long' ? 'var(--up)' : 'var(--down)',
        }}>
          {p.coin} {p.side === 'long' ? '↑' : '↓'}
        </span>
      ))}
      {positions.length > 5 && (
        <span style={{ color: 'var(--text-3)', fontSize: '0.7rem' }}>+{positions.length - 5}</span>
      )}
    </div>
  )
}

function ConsensusMeter({ data }: { data: Consensus }) {
  const color = data.consensus === 'long' ? 'var(--up)' : data.consensus === 'short' ? 'var(--down)' : 'var(--text-2)'
  const label = data.consensus === 'long' ? '롱 우세' : data.consensus === 'short' ? '숏 우세' : '중립'

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem' }}>고래 BTC 방향 합의</div>
        <div style={{ color, fontWeight: 700, fontSize: '0.9rem' }}>{label}</div>
      </div>
      <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 6 }}>
        <div style={{ width: `${data.long_pct}%`, background: 'var(--up)' }} />
        <div style={{ width: `${data.short_pct}%`, background: 'var(--down)' }} />
        <div style={{ flex: 1, background: 'var(--neutral-series)' }} />
      </div>
      <div style={{ display: 'flex', gap: 16, fontSize: '0.72rem' }}>
        <span style={{ color: 'var(--up)' }}>롱 {data.long_count}명 ({data.long_pct}%)</span>
        <span style={{ color: 'var(--down)' }}>숏 {data.short_count}명 ({data.short_pct}%)</span>
        <span style={{ color: 'var(--text-3)' }}>중립 {data.neutral_count}명</span>
      </div>
    </div>
  )
}

function formatEok(value: number | null | undefined) {
  if (value == null) return '-'
  return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}억`
}

function FlowChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
      <div style={{ color: 'var(--text-3)', fontSize: '0.72rem', marginBottom: 4 }}>{label}</div>
      <div style={{ color, fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700 }}>{changeArrow(value)} {formatEok(value)}</div>
    </div>
  )
}

function KrInvestorFlowView({
  data,
  market,
  onMarketChange,
}: {
  data: KrInvestorFlowData
  market: KrMarket
  onMarketChange: (market: KrMarket) => void
}) {
  const chartData = data.records.reduce<Array<KrInvestorFlowRecord & { dateLabel: string; cumulative_net: number }>>((items, record) => {
    const cumulativeNet = (items.at(-1)?.cumulative_net ?? 0) + record.foreign_net + record.institution_net
    items.push({
      ...record,
      dateLabel: record.date.slice(5),
      cumulative_net: cumulativeNet,
    })
    return items
  }, [])
  const latest = data.records.at(-1)
  const foreignTotal = data.records.reduce((sum, record) => sum + record.foreign_net, 0)
  const institutionTotal = data.records.reduce((sum, record) => sum + record.institution_net, 0)
  const individualTotal = data.records.reduce((sum, record) => sum + record.individual_net, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>
          네이버 투자자별 순매수 · 단위 억원
          {data.stale && <span style={{ color: 'var(--warn)', marginLeft: 8 }}>데이터 확인 필요</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {(['KOSPI', 'KOSDAQ'] as const).map(item => {
            const active = market === item
            return (
              <button
                key={item}
                type="button"
                onClick={() => onMarketChange(item)}
                style={{
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
                  background: active ? softBg(C.accent, 0.12) : 'var(--bg-inset)',
                  color: active ? 'var(--text)' : 'var(--text-2)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {item}
              </button>
            )
          })}
        </div>
      </div>

      <div className="grid-4" style={{ gap: 10 }}>
        <FlowChip label="외국인 누적" value={foreignTotal} color={changeColor(foreignTotal)} />
        <FlowChip label="기관 누적" value={institutionTotal} color={changeColor(institutionTotal)} />
        <FlowChip label="개인 누적" value={individualTotal} color={changeColor(individualTotal)} />
        <FlowChip label="최근 개인" value={latest?.individual_net ?? 0} color={changeColor(latest?.individual_net ?? 0)} />
      </div>

      <Card>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
          {data.market} 외국인·기관 순매수와 개인 보조 추이
        </div>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={C.line} vertical={false} />
              <XAxis dataKey="dateLabel" tick={{ fill: C.text3, fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis yAxisId="flow" tick={{ fill: C.text2, fontSize: 10 }} tickFormatter={v => `${v}`} width={48} />
              <YAxis yAxisId="cum" orientation="right" tick={{ fill: C.text2, fontSize: 10 }} tickFormatter={v => `${v}`} width={48} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                labelStyle={{ color: C.text2 }}
                formatter={(value, name) => [formatEok(Number(value)), name as string]}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: C.text2 }} />
              <ReferenceLine yAxisId="flow" y={0} stroke={C.text3} strokeDasharray="3 3" />
              <Bar yAxisId="flow" dataKey="foreign_net" fill={softBg(C.accent, 0.72)} name="외국인" barSize={9} />
              <Bar yAxisId="flow" dataKey="institution_net" fill={softBg(C.neutralSeries, 0.72)} name="기관" barSize={9} />
              <Line yAxisId="flow" type="monotone" dataKey="individual_net" stroke={C.text2} strokeWidth={1.5} dot={false} name="개인" />
              <Line yAxisId="cum" type="monotone" dataKey="cumulative_net" stroke={C.info} strokeWidth={2} dot={false} name="외국인+기관 누적" />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '56px 0', fontSize: '0.85rem' }}>
            수급 데이터가 없습니다
          </div>
        )}
      </Card>
    </div>
  )
}

function UsInsiderView({ data }: { data: UsInsiderData }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>
        SEC EDGAR Form 4 · 관심종목 내부자 장내 매매 · 최근 90일
      </div>

      <div className="grid-4" style={{ gap: 10 }}>
        {data.summaries.map(s => (
          <div key={s.ticker} style={{ background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ color: 'var(--text-3)', fontSize: '0.72rem', marginBottom: 4 }}>
              {s.name} <span style={{ color: 'var(--text-3)' }}>({s.trade_count}건)</span>
            </div>
            <div style={{ color: changeColor(s.net_value), fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700 }}>
              {changeArrow(s.net_value)} {s.net_value >= 0 ? '+' : ''}{fmt(s.net_value)}
            </div>
          </div>
        ))}
      </div>

      <Card>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
          내부자 거래 내역 (거래일 역순)
        </div>
        {data.trades.length > 0 ? (
          <div className="table-scroll">
            <div style={{
              display: 'grid',
              gridTemplateColumns: '80px 70px 1fr 70px 90px 90px',
              gap: 8, padding: '4px 8px',
              color: 'var(--text-3)', fontSize: '0.7rem', marginBottom: 6,
              borderBottom: '1px solid var(--line)',
              minWidth: 560,
            }}>
              <span>거래일</span>
              <span>종목</span>
              <span>내부자 (직함)</span>
              <span style={{ textAlign: 'center' }}>구분</span>
              <span style={{ textAlign: 'right' }}>수량</span>
              <span style={{ textAlign: 'right' }}>금액</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 560 }}>
              {data.trades.map((t, i) => (
                <div
                  key={i}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '80px 70px 1fr 70px 90px 90px',
                    gap: 8, padding: '8px 8px', borderRadius: 8,
                    background: 'var(--bg-inset)', alignItems: 'center',
                    fontSize: '0.78rem',
                  }}
                >
                  <span style={{ color: 'var(--text-2)' }}>{t.transaction_date.slice(5)}</span>
                  <span style={{ color: 'var(--text)', fontWeight: 600 }}>{t.ticker}</span>
                  <div>
                    <div style={{ color: 'var(--text)' }}>{t.insider_name}</div>
                    {t.insider_title && (
                      <div style={{ color: 'var(--text-3)', fontSize: '0.7rem' }}>{t.insider_title}</div>
                    )}
                  </div>
                  <span style={{
                    textAlign: 'center', fontWeight: 600,
                    color: t.code === 'P' ? 'var(--up)' : 'var(--down)',
                  }}>
                    {t.code === 'P' ? '매수' : '매도'}
                  </span>
                  <span style={{ color: 'var(--text-2)', textAlign: 'right' }}>
                    {t.shares != null ? t.shares.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—'}
                  </span>
                  <span style={{
                    textAlign: 'right', fontWeight: 600,
                    color: t.code === 'P' ? 'var(--up)' : 'var(--down)', fontFamily: 'var(--font-mono)',
                  }}>
                    {fmt(t.value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '40px 0', fontSize: '0.85rem' }}>
            내부자 거래 없음 (최근 90일)
          </div>
        )}
      </Card>
    </div>
  )
}

function Us13fView({ data }: { data: Us13fData }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>
        기관 보유 (13F) · 분기 · 45일 지연 · SEC EDGAR
      </div>

      <div className="grid-4" style={{ gap: 10 }}>
        {data.summaries.map(summary => (
          <div key={summary.ticker} style={{ background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ color: 'var(--text-3)', fontSize: '0.72rem', marginBottom: 4 }}>
              {summary.ticker} · {summary.latest_quarter ?? '분기 없음'}
            </div>
            <div style={{ color: 'var(--text)', fontSize: '1rem', fontWeight: 700 }}>
              {fmt(summary.latest_value)}
            </div>
            <div style={{ color: summary.qoq_change == null ? 'var(--text-3)' : changeColor(summary.qoq_change), fontFamily: 'var(--font-mono)', fontSize: '0.7rem', marginTop: 3 }}>
              QoQ {summary.qoq_change == null ? '—' : `${changeArrow(summary.qoq_change)} ${summary.qoq_change >= 0 ? '+' : ''}${summary.qoq_change.toFixed(1)}%`}
            </div>
          </div>
        ))}
      </div>

      <Card>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
          기관별 보유 내역 (최신 4분기)
        </div>
        {data.holdings.length > 0 ? (
          <div className="table-scroll">
            <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 70px 100px 110px', gap: 8, padding: '4px 8px', color: 'var(--text-3)', fontSize: '0.7rem', marginBottom: 6, borderBottom: '1px solid var(--line)', minWidth: 560 }}>
              <span>분기</span><span>기관</span><span>종목</span>
              <span style={{ textAlign: 'right' }}>수량</span><span style={{ textAlign: 'right' }}>가치</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 560 }}>
              {data.holdings.map(holding => (
                <div key={`${holding.accession_no}-${holding.seq}`} style={{ display: 'grid', gridTemplateColumns: '90px 1fr 70px 100px 110px', gap: 8, padding: '8px', borderRadius: 8, background: 'var(--bg-inset)', alignItems: 'center', fontSize: '0.78rem' }}>
                  <span style={{ color: 'var(--text-2)' }}>{holding.quarter}</span>
                  <span style={{ color: 'var(--text-2)' }}>{holding.institution}</span>
                  <span style={{ color: 'var(--text)', fontWeight: 600 }}>{holding.ticker}{holding.put_call === 'Call' ? ' Call' : ''}</span>
                  <span style={{ color: 'var(--text-2)', textAlign: 'right' }}>{holding.shares?.toLocaleString('en-US', { maximumFractionDigits: 0 }) ?? '—'}</span>
                  <span style={{ color: 'var(--text)', textAlign: 'right', fontWeight: 600 }}>{fmt(holding.value_usd)}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '40px 0', fontSize: '0.85rem' }}>
            기관 보유 데이터가 없습니다
          </div>
        )}
      </Card>
    </div>
  )
}

function CoinWhaleView({
  data,
  consensus,
  lastUpdated,
}: {
  data: WhaleData
  consensus: Consensus | null
  lastUpdated: Date | null
}) {
  const { whales } = data

  return (
    <>
      <LastUpdated timestamp={lastUpdated} />
      {consensus && consensus.total > 0 && (
        <Card>
          <ConsensusMeter data={consensus} />
        </Card>
      )}

      <Card>
        <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', marginBottom: 12 }}>
          Hyperliquid 고래 TOP {whales.length} (실시간)
        </div>

        <div className="table-scroll">
          <div style={{
            display: 'grid',
            gridTemplateColumns: '32px 1fr 90px 90px 80px 90px 1fr',
            gap: 8, padding: '4px 8px',
            color: 'var(--text-3)', fontSize: '0.7rem', marginBottom: 6,
            borderBottom: '1px solid var(--line)',
            minWidth: 580,
          }}>
            <span>#</span>
            <span>주소 / 닉네임</span>
            <span style={{ textAlign: 'right' }}>자산</span>
            <span style={{ textAlign: 'right' }}>30d PnL</span>
            <span style={{ textAlign: 'right' }}>30d ROI</span>
            <span style={{ textAlign: 'center' }}>BTC</span>
            <span>포지션</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 580 }}>
            {whales.map((w) => (
              <div
                key={w.address}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '32px 1fr 90px 90px 80px 90px 1fr',
                  gap: 8, padding: '8px 8px', borderRadius: 8,
                  background: 'var(--bg-inset)', alignItems: 'center',
                }}
              >
                <span style={{ color: w.rank <= 3 ? 'var(--accent)' : 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', fontWeight: 700 }}>
                  {w.rank}
                </span>

                <div>
                  {w.display_name ? (
                    <div style={{ color: 'var(--text)', fontSize: '0.82rem', fontWeight: 600 }}>{w.display_name}</div>
                  ) : null}
                  <div style={{ color: 'var(--text-3)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)' }}>
                    {w.address.slice(0, 6)}…{w.address.slice(-4)}
                  </div>
                </div>

                <span style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', textAlign: 'right' }}>
                  {fmt(w.account_value)}
                </span>

                <span style={{
                  color: changeColor(w.pnl_30d ?? 0), fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem', textAlign: 'right', fontWeight: 600,
                }}>
                  {fmt(w.pnl_30d)}
                </span>

                <span style={{
                  color: changeColor(w.roi_30d ?? 0), fontFamily: 'var(--font-mono)',
                  fontSize: '0.78rem', textAlign: 'right',
                }}>
                  {w.roi_30d != null ? `${(w.roi_30d * 100).toFixed(1)}%` : '—'}
                </span>

                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <BtcBadge pos={w.btc_position} />
                </div>

                <PositionList positions={w.positions} />
              </div>
            ))}
          </div>
        </div>
      </Card>

      {whales.length === 0 && (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: 24 }}>
          고래 데이터를 불러오지 못했습니다
        </div>
      )}
    </>
  )
}

export function Whale() {
  const [asset, setAsset] = useState<AssetTab>(() => readAssetTab(['coin', 'kr', 'us']))
  const [krMarket, setKrMarket] = useState<KrMarket>('KOSPI')
  const coinApi = useApi<WhaleData>(asset === 'coin' ? '/api/hyperliquid-whales' : null, 120_000)
  const consensusApi = useApi<Consensus>(asset === 'coin' ? '/api/whale-consensus' : null, 120_000)
  const krApi = useApi<KrInvestorFlowData>(
    asset === 'kr' ? `/api/whale/kr-investor-flow?market=${krMarket}&days=30` : null,
    300_000,
  )
  const usApi = useApi<UsInsiderData>(asset === 'us' ? '/api/whale/us-insider-trades' : null, 300_000)
  const us13fApi = useApi<Us13fData>(asset === 'us' ? '/api/whale/us-13f-holdings' : null, 300_000)

  function handleAssetChange(next: AssetTab) {
    setAsset(next)
    replaceAssetTab(next)
  }

  const tabs = <AssetTabs asset={asset} allowedTabs={['coin', 'kr', 'us']} onChange={handleAssetChange} />

  if (asset === 'us') {
    if ((usApi.error && !usApi.data) || (us13fApi.error && !us13fApi.data)) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tabs}
          <ErrorState
            error={usApi.error ?? us13fApi.error ?? '데이터를 불러오지 못했습니다'}
            onRetry={() => { usApi.refetch(); us13fApi.refetch() }}
          />
        </div>
      )
    }
    if (usApi.loading || !usApi.data || us13fApi.loading || !us13fApi.data) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tabs}
          <Skeleton />
        </div>
      )
    }

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <LastUpdated timestamp={usApi.lastUpdated} />
        <UsInsiderView data={usApi.data} />
        <Us13fView data={us13fApi.data} />
      </div>
    )
  }

  if (asset === 'kr') {
    if (krApi.error && !krApi.data) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tabs}
          <ErrorState error={krApi.error} onRetry={krApi.refetch} />
        </div>
      )
    }
    if (krApi.loading || !krApi.data) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tabs}
          <Skeleton />
        </div>
      )
    }

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <LastUpdated timestamp={krApi.lastUpdated} />
        <KrInvestorFlowView data={krApi.data} market={krMarket} onMarketChange={setKrMarket} />
      </div>
    )
  }

  if (coinApi.error && !coinApi.data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <ErrorState error={coinApi.error} onRetry={coinApi.refetch} />
      </div>
    )
  }
  if (coinApi.loading || !coinApi.data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {tabs}
        <Skeleton />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {tabs}
      <CoinWhaleView
        data={coinApi.data}
        consensus={consensusApi.data}
        lastUpdated={coinApi.lastUpdated}
      />
    </div>
  )
}
