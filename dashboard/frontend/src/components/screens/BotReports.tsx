import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { BOT_REPORT_KINDS, formatKst, kindLabel, parseReportBody, previewOf } from './botReportView'
import type { Block, Inline } from './botReportView'

interface BotReport {
  id: number
  kind: string
  title: string
  body: string
  reported_at: string
  received_at: string
}

interface BotReportsData {
  reports: BotReport[]
}

function Inlines({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((part, i) => {
        if (part.href) {
          return (
            <a key={i} href={part.href} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
              style={{ color: 'var(--accent)', textDecoration: 'underline' }}>
              {part.text}
            </a>
          )
        }
        return part.bold
          ? <strong key={i} style={{ color: 'var(--text)', fontWeight: 700 }}>{part.text}</strong>
          : <span key={i}>{part.text}</span>
      })}
    </>
  )
}

function BodyBlock({ block }: { block: Block }) {
  if (block.type === 'heading') {
    return <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}><Inlines parts={block.inlines} /></div>
  }
  if (block.type === 'list') {
    return (
      <ul style={{ margin: 0, paddingLeft: 18, listStyle: 'disc', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {block.items.map((item, i) => <li key={i}><Inlines parts={item} /></li>)}
      </ul>
    )
  }
  if (block.type === 'table') {
    // 표는 카드 안에서만 가로로 넘겨 본다 — 화면 전체가 옆으로 밀리지 않게
    return (
      <div className="bot-report-table-wrap">
        <table className="bot-report-table">
          <thead>
            <tr>{block.header.map((cell, i) => <th key={i}><Inlines parts={cell} /></th>)}</tr>
          </thead>
          <tbody>
            {block.rows.map((row, r) => (
              <tr key={r}>{row.map((cell, c) => <td key={c}><Inlines parts={cell} /></td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return <div><Inlines parts={block.inlines} /></div>
}

function ReportCard({ report, expanded, onToggle }: { report: BotReport; expanded: boolean; onToggle: () => void }) {
  const preview = previewOf(report.body)
  return (
    <div
      onClick={onToggle}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-card)',
        borderRadius: 16,
        padding: '18px 20px',
        cursor: 'pointer',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{
          background: 'var(--seg-active)', color: 'var(--text-2)', border: '1px solid var(--border)',
          borderRadius: 6, padding: '2px 8px', fontSize: 12, fontWeight: 600,
        }}>{kindLabel(report.kind)}</span>
        <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{formatKst(report.reported_at)}</span>
      </div>

      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', lineHeight: 1.4 }}>{report.title}</div>

      {!expanded && preview && (
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginTop: 6 }}>{preview}</div>
      )}

      {expanded && (
        <div style={{
          marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--line)',
          display: 'flex', flexDirection: 'column', gap: 10,
          fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6, overflowWrap: 'anywhere',
        }}>
          {parseReportBody(report.body).map((block, i) => <BodyBlock key={i} block={block} />)}
        </div>
      )}

      {/* 클릭은 카드의 onClick이 받는다 — 키보드·보조기기용 버튼 */}
      <button type="button" aria-expanded={expanded} className="research-detail-btn">
        {expanded ? '▲ 접기' : '▼ 펼치기'}
      </button>
    </div>
  )
}

export function BotReports() {
  const [kind, setKind] = useState<string | null>(null)
  // 펼침 상태를 손댄 카드만 기억한다 — 손대지 않은 동안은 맨 위(가장 최근) 한 건만 펼쳐 둔다
  const [toggled, setToggled] = useState<Record<number, boolean>>({})
  const url = kind ? `/api/bot-reports?kind=${kind}&limit=100` : '/api/bot-reports?limit=100'
  const { data, error, refetch, lastUpdated } = useApi<BotReportsData>(url, 60_000)

  // 종류 칩 — 뼈대·오류 화면에서도 보여 실패한 종류에서 빠져나올 수 있게 한다
  const chips = (
    <div role="group" aria-label="종류로 걸러 보기" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      <button type="button" className="v2-chip" aria-pressed={kind === null} onClick={() => setKind(null)}>전체</button>
      {BOT_REPORT_KINDS.map(k => (
        <button key={k.value} type="button" className="v2-chip" aria-pressed={kind === k.value} onClick={() => setKind(k.value)}>
          {k.label}
        </button>
      ))}
    </div>
  )

  if (!data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {chips}
        {error ? <ErrorState error={error} onRetry={refetch} /> : <Skeleton />}
      </div>
    )
  }

  const reports = data.reports ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} failed={!!error} />

      <span style={{ color: 'var(--text-2)', fontSize: 13 }}>
        최근 <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)', fontWeight: 600 }}>{reports.length}</span>건 · 시각 KST · 봇이 보낸 원문 그대로
      </span>

      {chips}

      {reports.length === 0 ? (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16,
          padding: '32px 20px', textAlign: 'center', color: 'var(--text-2)', fontSize: 13, lineHeight: 1.7,
        }}>
          {kind ? `'${kindLabel(kind)}' 리포트가 아직 없습니다.` : '아직 받은 리포트가 없습니다.'}
          <br />봇이 보내기 시작하면 여기에 쌓입니다.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {reports.map((report, i) => (
            <ReportCard
              key={report.id}
              report={report}
              expanded={toggled[report.id] ?? i === 0}
              onToggle={() => setToggled(prev => ({ ...prev, [report.id]: !(prev[report.id] ?? i === 0) }))}
            />
          ))}
        </div>
      )}
    </div>
  )
}
