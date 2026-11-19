import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { Modal } from './Modal'
import { useApi } from '../../hooks/useApi'
import { C } from '../../lib/theme'

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
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em' }}>지수 차트</div>
          <div style={{ color: 'var(--text)', fontSize: '1.1rem', fontWeight: 700, marginTop: 2 }}>{name}</div>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: '1.5rem', cursor: 'pointer', lineHeight: 1 }}
        >
          ×
        </button>
      </div>

      {/* 차트 영역 */}
      <div style={{ flex: 1, padding: '20px', overflow: 'hidden' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)' }}>
            로딩 중...
          </div>
        )}
        {!loading && chartData.length === 0 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)' }}>
            데이터 없음
          </div>
        )}
        {!loading && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.line} />
              <XAxis
                dataKey="date"
                tick={{ fill: C.text3, fontSize: 10, fontFamily: 'var(--font-mono)' }}
                interval="preserveStartEnd"
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis
                tick={{ fill: C.text3, fontSize: 10, fontFamily: 'var(--font-mono)' }}
                width={60}
                tickFormatter={(v: number) => v.toLocaleString()}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: '0.8rem' }}
                labelStyle={{ color: C.text2 }}
                formatter={(v) => [Number(v).toLocaleString(), name]}
              />
              <Line type="monotone" dataKey="close" stroke={C.info} strokeWidth={2} dot={false} name={name} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Modal>
  )
}
