import { getJournal } from '../../lib/learningApi.ts'
import type { JournalEntry } from '../../lib/learningApi.ts'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import { SkeletonCard } from '../shared/Skeleton'
import { PHASE_LABELS } from './learningChartData.ts'
import {
  DIM, fmtDateTime, fmtPrice, fmtQty, noteStyle, rationaleText, tdStyle, thStyle, useLoader,
} from './learningShared.ts'

// 매매 일지 — 포지션(최근 진입순)별 체결과 그때의 근거
export function JournalPanel() {
  const journal = useLoader(getJournal)

  if (journal.error) return <ErrorState error={journal.error} onRetry={journal.reload} />
  if (!journal.data) return <SkeletonCard height={200} />
  if (journal.data.length === 0) {
    return <Card><div style={noteStyle}>아직 기록이 없습니다. 매매 탭에서 근거와 함께 첫 주문을 넣어 보세요.</div></Card>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {journal.data.map(entry => <JournalCard key={entry.position.id} entry={entry} />)}
    </div>
  )
}

function JournalCard({ entry }: { entry: JournalEntry }) {
  const { position: p, fills } = entry
  return (
    <Card>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'baseline', marginBottom: 8, fontSize: '0.85rem' }}>
        <b style={{ color: '#e2e8f0' }}>#{p.id} {p.symbol}</b>
        <span style={{ color: p.status === 'open' ? '#60a5fa' : DIM }}>{p.status === 'open' ? '보유 중' : '청산'}</span>
        <span style={{ color: '#cbd5e1' }}>진입 국면 {PHASE_LABELS[p.entry_phase]}</span>
        <span style={{ color: DIM }}>첫 진입 {fmtDateTime(p.opened_at)} · {fmtPrice(p.first_entry_price)}</span>
        {p.closed_at && <span style={{ color: DIM }}>청산 {fmtDateTime(p.closed_at)}</span>}
      </div>
      <div className="table-scroll">
        <table style={{ width: '100%', minWidth: 720, borderCollapse: 'collapse', fontSize: '0.78rem' }}>
          <thead>
            <tr style={{ color: DIM, textAlign: 'right', borderBottom: '1px solid #334155', whiteSpace: 'nowrap' }}>
              <th style={{ ...thStyle, textAlign: 'left' }}>시각</th>
              <th style={{ ...thStyle, textAlign: 'left' }}>방향</th>
              <th style={thStyle}>수량</th>
              <th style={thStyle}>가격</th>
              <th style={thStyle}>금액 (USDT · 매수=수수료 포함, 매도=수수료 전)</th>
              <th style={thStyle}>수수료</th>
              <th style={{ ...thStyle, textAlign: 'left' }}>근거</th>
            </tr>
          </thead>
          <tbody>
            {fills.map(f => (
              <tr key={f.id} style={{ textAlign: 'right', borderBottom: '1px solid #334155', verticalAlign: 'top' }}>
                <td style={{ ...tdStyle, textAlign: 'left', whiteSpace: 'nowrap' }}>{fmtDateTime(f.executed_at)}</td>
                <td style={{ ...tdStyle, textAlign: 'left', color: f.side === 'buy' ? '#4ade80' : '#f87171' }}>
                  {f.side === 'buy' ? '매수' : '매도'}
                </td>
                <td style={tdStyle}>{fmtQty(f.qty)}</td>
                <td style={tdStyle}>{fmtPrice(f.price)}</td>
                <td style={tdStyle}>{f.usdt_amount.toFixed(2)}</td>
                <td style={tdStyle}>{f.fee_usdt.toFixed(2)}</td>
                <td style={{ ...tdStyle, textAlign: 'left' }}>
                  <div>{rationaleText(f.phase, f.ichimoku)}</div>
                  {f.memo && <div style={{ color: '#94a3b8', marginTop: 2, whiteSpace: 'pre-wrap' }}>메모: {f.memo}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
