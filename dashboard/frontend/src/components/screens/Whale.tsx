import { useApi } from '../../hooks/useApi'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'

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

function fmt(v: number | null, decimals = 2): string {
  if (v == null) return '—'
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`
  if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
  return `$${v.toFixed(decimals)}`
}

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

export function Whale() {
  const { data, loading, error, refetch } = useApi<WhaleData>('/api/hyperliquid-whales', 120_000)
  const { data: consensus } = useApi<Consensus>('/api/whale-consensus', 120_000)

  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (loading || !data) return <Skeleton />

  const { whales } = data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* 합의 미터 */}
      {consensus && consensus.total > 0 && (
        <Card>
          <ConsensusMeter data={consensus} />
        </Card>
      )}

      {/* 고래 리더보드 */}
      <Card>
        <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: 12 }}>
          Hyperliquid 고래 TOP {whales.length} (실시간)
        </div>

        {/* 헤더 */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '32px 1fr 90px 90px 80px 90px 1fr',
          gap: 8, padding: '4px 8px',
          color: '#64748b', fontSize: '0.7rem', marginBottom: 6,
          borderBottom: '1px solid #1e293b',
        }}>
          <span>#</span>
          <span>주소 / 닉네임</span>
          <span style={{ textAlign: 'right' }}>자산</span>
          <span style={{ textAlign: 'right' }}>30d PnL</span>
          <span style={{ textAlign: 'right' }}>30d ROI</span>
          <span style={{ textAlign: 'center' }}>BTC</span>
          <span>포지션</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
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
              {/* 순위 */}
              <span style={{ color: w.rank <= 3 ? '#f59e0b' : '#64748b', fontSize: '0.8rem', fontWeight: 700 }}>
                {w.rank}
              </span>

              {/* 주소/닉네임 */}
              <div>
                {w.display_name ? (
                  <div style={{ color: '#e2e8f0', fontSize: '0.82rem', fontWeight: 600 }}>{w.display_name}</div>
                ) : null}
                <div style={{ color: '#64748b', fontSize: '0.7rem', fontFamily: 'monospace' }}>
                  {w.address.slice(0, 6)}…{w.address.slice(-4)}
                </div>
              </div>

              {/* 자산 */}
              <span style={{ color: '#e2e8f0', fontSize: '0.8rem', textAlign: 'right' }}>
                {fmt(w.account_value)}
              </span>

              {/* 30d PnL */}
              <span style={{
                color: (w.pnl_30d ?? 0) >= 0 ? '#4ade80' : '#f87171',
                fontSize: '0.8rem', textAlign: 'right', fontWeight: 600,
              }}>
                {fmt(w.pnl_30d)}
              </span>

              {/* 30d ROI */}
              <span style={{
                color: (w.roi_30d ?? 0) >= 0 ? '#4ade80' : '#f87171',
                fontSize: '0.78rem', textAlign: 'right',
              }}>
                {w.roi_30d != null ? `${(w.roi_30d * 100).toFixed(1)}%` : '—'}
              </span>

              {/* BTC 포지션 */}
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <BtcBadge pos={w.btc_position} />
              </div>

              {/* 전체 포지션 */}
              <PositionList positions={w.positions} />
            </div>
          ))}
        </div>
      </Card>

      {whales.length === 0 && (
        <div style={{ color: '#64748b', textAlign: 'center', padding: 24 }}>
          고래 데이터를 불러오지 못했습니다
        </div>
      )}

    </div>
  )
}
