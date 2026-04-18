import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { Modal } from './Modal'
import { useApi } from '../../hooks/useApi'

interface HistoryPoint {
  date: string
  close: number
}

interface HistoryResponse {
  ticker: string
  history: HistoryPoint[]
}

interface StockIndexModalProps {
  ticker: string | null
  name: string
  onClose: () => void
}

export function StockIndexModal({ ticker, name, onClose }: StockIndexModalProps) {
  const { data, loading } = useApi<HistoryResponse>(
    ticker ? `/api/stock-index-history/${encodeURIComponent(ticker)}` : null,
    3_600_000
  )

  const chartData = data?.history ?? []

  return (
    <Modal open={ticker !== null} onClose={onClose}>
      {/* 헤더 */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em' }}>지수 차트</div>
          <div style={{ color: '#e2e8f0', fontSize: '1.1rem', fontWeight: 700, marginTop: 2 }}>{name}</div>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '1.5rem', cursor: 'pointer', lineHeight: 1 }}
        >
          ×
        </button>
      </div>

      {/* 차트 영역 */}
      <div style={{ flex: 1, padding: '20px', overflow: 'hidden' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b' }}>
            로딩 중...
          </div>
        )}
        {!loading && chartData.length === 0 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b' }}>
            데이터 없음
          </div>
        )}
        {!loading && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 10 }}
                interval="preserveStartEnd"
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 10 }}
                width={60}
                tickFormatter={(v: number) => v.toLocaleString()}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: '0.8rem' }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v: number) => [v.toLocaleString(), name]}
              />
              <Line type="monotone" dataKey="close" stroke="#60a5fa" strokeWidth={2} dot={false} name={name} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Modal>
  )
}
