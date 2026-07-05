export interface PutcallRecord {
  date: string
  total_pc: number | null
  equity_pc: number | null
  index_pc: number | null
}

export type PutcallSeries = 'equity' | 'total' | 'index'

export function describePutcall(value: number | null) {
  if (value == null) {
    return { label: '데이터 없음', color: '#64748b', help: '-' }
  }
  if (value < 0.7) {
    return { label: '과열', color: '#f87171', help: '0.7 미만' }
  }
  if (value > 1.0) {
    return { label: '공포', color: '#4ade80', help: '1.0 초과' }
  }
  return { label: '중립', color: '#94a3b8', help: '0.7~1.0' }
}

export function toPutcallChartRows(records: PutcallRecord[]) {
  return records.map(record => ({
    date: record.date.slice(5),
    total: record.total_pc,
    equity: record.equity_pc,
    index: record.index_pc,
  }))
}
