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

function BtcBadge({ pos }: { pos: Position | null }) {
  if (!pos) return <span style={{ color: '#64748b', fontSize: '0.75rem' }}>—</span>
  const color = pos.side === 'long' ? '#4ade80' : '#f87171'
  const label = pos.side === 'long' ? '롱' : '숏'
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 6, fontSize: '0.72rem', fontWeight: 600,
      background: pos.side === 'long' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
      color,
    }}>
      BTC {label}
      {pos.leverage != null && ` ${pos.leverage.toFixed(0)}x`}
    </span>
  )
}

function PositionList({ positions }: { positions: Position[] }) {
  if (!positions || positions.length === 0) {
    return <span style={{ color: '#64748b', fontSize: '0.75rem' }}>포지션 없음</span>
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {positions.slice(0, 5).map((p, i) => (
        <span key={i} style={{
          padding: '1px 7px', borderRadius: 5, fontSize: '0.7rem',
          background: p.side === 'long' ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
          color: p.side === 'long' ? '#4ade80' : '#f87171',
        }}>
          {p.coin} {p.side === 'long' ? '↑' : '↓'}
        </span>
      ))}
      {positions.length > 5 && (
        <span style={{ color: '#64748b', fontSize: '0.7rem' }}>+{positions.length - 5}</span>
      )}
    </div>
  )
}

function ConsensusMeter({ data }: { data: Consensus }) {
  const color = data.consensus === 'long' ? '#4ade80' : data.consensus === 'short' ? '#f87171' : '#94a3b8'
  const label = data.consensus === 'long' ? '롱 우세' : data.consensus === 'short' ? '숏 우세' : '중립'

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}>
        <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>고래 BTC 방향 합의</div>
        <div style={{ color, fontWeight: 700, fontSize: '0.9rem' }}>{label}</div>
      </div>
      <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 6 }}>
        <div style={{ width: `${data.long_pct}%`, background: '#4ade80' }} />
        <div style={{ width: `${data.short_pct}%`, background: '#f87171' }} />
        <div style={{ flex: 1, background: '#334155' }} />
      </div>
      <div style={{ display: 'flex', gap: 16, fontSize: '0.72rem' }}>
        <span style={{ color: '#4ade80' }}>롱 {data.long_count}명 ({data.long_pct}%)</span>
        <span style={{ color: '#f87171' }}>숏 {data.short_count}명 ({data.short_pct}%)</span>
        <span style={{ color: '#64748b' }}>중립 {data.neutral_count}명</span>
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
    <div style={{ background: '#0f1117', border: '1px solid #1e293b', borderRadius: 8, padding: '10px 12px' }}>
      <div style={{ color: '#64748b', fontSize: '0.72rem', marginBottom: 4 }}>{label}</div>
      <div style={{ color, fontSize: '1rem', fontWeight: 700 }}>{formatEok(value)}</div>
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
        <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
          네이버 투자자별 순매수 · 단위 억원
          {data.stale && <span style={{ color: '#f59e0b', marginLeft: 8 }}>데이터 확인 필요</span>}
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
                  border: `1px solid ${active ? '#38bdf8' : '#334155'}`,
                  background: active ? 'rgba(56,189,248,0.12)' : '#0f172a',
                  color: active ? '#e0f2fe' : '#94a3b8',
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
        <FlowChip label="외국인 누적" value={foreignTotal} color={foreignTotal >= 0 ? '#4ade80' : '#f87171'} />
        <FlowChip label="기관 누적" value={institutionTotal} color={institutionTotal >= 0 ? '#60a5fa' : '#f87171'} />
        <FlowChip label="개인 누적" value={individualTotal} color={individualTotal >= 0 ? '#f59e0b' : '#94a3b8'} />
        <FlowChip label="최근 개인" value={latest?.individual_net ?? 0} color={(latest?.individual_net ?? 0) >= 0 ? '#f59e0b' : '#94a3b8'} />
      </div>

      <Card>
        <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
          {data.market} 외국인·기관 순매수와 개인 보조 추이
        </div>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1e293b" vertical={false} />
              <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis yAxisId="flow" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `${v}`} width={48} />
              <YAxis yAxisId="cum" orientation="right" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `${v}`} width={48} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(value, name) => [formatEok(Number(value)), name as string]}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem', color: '#94a3b8' }} />
              <ReferenceLine yAxisId="flow" y={0} stroke="#475569" strokeDasharray="3 3" />
              <Bar yAxisId="flow" dataKey="foreign_net" fill="rgba(74,222,128,0.72)" name="외국인" barSize={9} />
              <Bar yAxisId="flow" dataKey="institution_net" fill="rgba(96,165,250,0.72)" name="기관" barSize={9} />
              <Line yAxisId="flow" type="monotone" dataKey="individual_net" stroke="#94a3b8" strokeWidth={1.5} dot={false} name="개인" />
              <Line yAxisId="cum" type="monotone" dataKey="cumulative_net" stroke="#f59e0b" strokeWidth={2} dot={false} name="외국인+기관 누적" />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ color: '#64748b', textAlign: 'center', padding: '56px 0', fontSize: '0.85rem' }}>
            수급 데이터가 없습니다
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
        <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
          Hyperliquid 고래 TOP {whales.length} (실시간)
        </div>

        <div className="table-scroll">
          <div style={{
            display: 'grid',
            gridTemplateColumns: '32px 1fr 90px 90px 80px 90px 1fr',
            gap: 8, padding: '4px 8px',
            color: '#64748b', fontSize: '0.7rem', marginBottom: 6,
            borderBottom: '1px solid #1e293b',
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
                  background: '#0f1117', alignItems: 'center',
                }}
              >
                <span style={{ color: w.rank <= 3 ? '#f59e0b' : '#64748b', fontSize: '0.8rem', fontWeight: 700 }}>
                  {w.rank}
                </span>

                <div>
                  {w.display_name ? (
                    <div style={{ color: '#e2e8f0', fontSize: '0.82rem', fontWeight: 600 }}>{w.display_name}</div>
                  ) : null}
                  <div style={{ color: '#64748b', fontSize: '0.7rem', fontFamily: 'monospace' }}>
                    {w.address.slice(0, 6)}…{w.address.slice(-4)}
                  </div>
                </div>

                <span style={{ color: '#e2e8f0', fontSize: '0.8rem', textAlign: 'right' }}>
                  {fmt(w.account_value)}
                </span>

                <span style={{
                  color: (w.pnl_30d ?? 0) >= 0 ? '#4ade80' : '#f87171',
                  fontSize: '0.8rem', textAlign: 'right', fontWeight: 600,
                }}>
                  {fmt(w.pnl_30d)}
                </span>

                <span style={{
                  color: (w.roi_30d ?? 0) >= 0 ? '#4ade80' : '#f87171',
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
        <div style={{ color: '#64748b', textAlign: 'center', padding: 24 }}>
          고래 데이터를 불러오지 못했습니다
        </div>
      )}
    </>
  )
}

export function Whale() {
  const [asset, setAsset] = useState<AssetTab>(() => readAssetTab(['coin', 'kr']))
  const [krMarket, setKrMarket] = useState<KrMarket>('KOSPI')
  const coinApi = useApi<WhaleData>(asset === 'coin' ? '/api/hyperliquid-whales' : null, 120_000)
  const consensusApi = useApi<Consensus>(asset === 'coin' ? '/api/whale-consensus' : null, 120_000)
  const krApi = useApi<KrInvestorFlowData>(
    asset === 'kr' ? `/api/whale/kr-investor-flow?market=${krMarket}&days=30` : null,
    300_000,
  )

  function handleAssetChange(next: AssetTab) {
    setAsset(next)
    replaceAssetTab(next)
  }

  const tabs = <AssetTabs asset={asset} allowedTabs={['coin', 'kr']} onChange={handleAssetChange} />

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
