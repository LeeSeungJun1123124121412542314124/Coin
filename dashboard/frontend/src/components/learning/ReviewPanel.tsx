import { useCallback, useState } from 'react'
import { confirmReview, getJournal, getReviews } from '../../lib/learningApi.ts'
import type { JournalPosition, Review, Verdict } from '../../lib/learningApi.ts'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import { SkeletonCard } from '../shared/Skeleton'
import {
  DIM, MUTED, VERDICT_LABELS, buttonStyle, errorStyle, errorText, fmtDateTime, fmtPrice, fmtSignedPct, inputStyle,
  noteStyle, pnlArrow, pnlColor, rationaleText, useLoader,
} from './learningShared.ts'

const HORIZONS = [14, 28] as const
const VERDICTS = Object.keys(VERDICT_LABELS) as Verdict[]

// 복기 — 포지션마다 14·28일 기준일 종가로 결과를 보고, 제안 판정을 확정하거나 뒤집는다
export function ReviewPanel() {
  const journal = useLoader(getJournal)

  if (journal.error) return <ErrorState error={journal.error} onRetry={journal.reload} />
  if (!journal.data) return <SkeletonCard height={200} />
  if (journal.data.length === 0) {
    return <Card><div style={noteStyle}>복기할 포지션이 없습니다. 매매 탭에서 먼저 주문하세요.</div></Card>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {journal.data.map(e => <PositionReview key={e.position.id} position={e.position} />)}
    </div>
  )
}

function PositionReview({ position }: { position: JournalPosition }) {
  const load = useCallback(() => getReviews(position.id), [position.id])
  const reviews = useLoader(load)

  return (
    <Card>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'baseline', marginBottom: 10, fontSize: '0.85rem' }}>
        <b style={{ color: 'var(--text)' }}>#{position.id} {position.symbol}</b>
        <span style={{ color: DIM }}>첫 진입 {fmtDateTime(position.opened_at)} · {fmtPrice(position.first_entry_price)}</span>
        <span style={{ color: position.status === 'open' ? 'var(--accent)' : DIM }}>{position.status === 'open' ? '보유 중' : '청산'}</span>
      </div>
      {reviews.error ? (
        <div style={errorStyle}>{reviews.error}</div>
      ) : !reviews.data ? (
        <div style={noteStyle}>복기 불러오는 중...</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
          {HORIZONS.map(h => {
            const review = reviews.data?.[String(h)]
            return review ? (
              <HorizonReview key={h} positionId={position.id} horizon={h} review={review} onConfirmed={reviews.reload} />
            ) : null
          })}
        </div>
      )}
    </Card>
  )
}

function HorizonReview({ positionId, horizon, review, onConfirmed }: {
  positionId: number
  horizon: number
  review: Review
  onConfirmed: () => void
}) {
  const box = { background: 'var(--bg-inset)', borderRadius: 8, padding: '10px 12px', fontSize: '0.8rem', color: 'var(--text-2)' }
  if (review.status === 'pending') {
    return (
      <div style={box}>
        <b style={{ color: 'var(--text)' }}>{horizon}일 복기</b>
        <div style={{ color: MUTED, marginTop: 4 }}>대기 중 — 기준일 {review.due} (UTC, 그날 일봉 종가가 생기면 열립니다)</div>
      </div>
    )
  }
  return (
    <div style={box}>
      <b style={{ color: 'var(--text)' }}>{horizon}일 복기</b>
      <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div><span style={{ color: DIM }}>진입 근거 </span>{rationaleText(review.rationale.phase, review.rationale.ichimoku)}</div>
        {review.rationale.memo && <div style={{ whiteSpace: 'pre-wrap' }}><span style={{ color: DIM }}>메모 </span>{review.rationale.memo}</div>}
        <div><span style={{ color: DIM }}>기준일 종가 </span>{fmtPrice(review.close_price)}</div>
        <div>
          <span style={{ color: DIM }}>손익 (실현+평가) </span>
          <span style={{ color: pnlColor(review.pnl_usdt) }}>{pnlArrow(review.pnl_usdt)}{review.pnl_usdt.toFixed(2)} USDT</span>
        </div>
        <div>
          <span style={{ color: DIM }}>보유 가정 수익률 </span>
          <span style={{ color: pnlColor(review.hold_return_pct) }}>{pnlArrow(review.hold_return_pct)}{fmtSignedPct(review.hold_return_pct)}</span>
        </div>
        <div>
          <span style={{ color: DIM }}>제안 판정 </span>
          {review.suggested === null ? '없음 (국면 불명확)' : VERDICT_LABELS[review.suggested]}
        </div>
        {review.confirmed && (
          <div>
            <span style={{ color: DIM }}>확정 판정 </span><b>{VERDICT_LABELS[review.confirmed]}</b>
            {review.reason && <span style={{ color: MUTED }}> — {review.reason}</span>}
          </div>
        )}
      </div>
      {review.suggested === null ? (
        <div style={{ ...noteStyle, marginTop: 8 }}>국면이 불명확한 포지션은 판정하지 않습니다.</div>
      ) : (
        <ConfirmForm
          key={`${review.confirmed}-${review.reason}`}
          positionId={positionId}
          horizon={horizon}
          initialVerdict={review.confirmed ?? review.suggested}
          initialReason={review.reason ?? ''}
          confirmed={review.confirmed !== null}
          onConfirmed={onConfirmed}
        />
      )}
    </div>
  )
}

// 제안 판정 확정/수정 — 사유 필수, 400은 메시지 표시
function ConfirmForm({ positionId, horizon, initialVerdict, initialReason, confirmed, onConfirmed }: {
  positionId: number
  horizon: number
  initialVerdict: Verdict
  initialReason: string
  confirmed: boolean
  onConfirmed: () => void
}) {
  const [verdict, setVerdict] = useState<Verdict>(initialVerdict)
  const [reason, setReason] = useState(initialReason)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canSubmit = !busy && reason.trim() !== ''

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await confirmReview(positionId, horizon, verdict, reason.trim())
      onConfirmed()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <select style={inputStyle} aria-label="판정" value={verdict} onChange={e => setVerdict(e.target.value as Verdict)}>
          {VERDICTS.map(v => <option key={v} value={v}>{VERDICT_LABELS[v]}</option>)}
        </select>
        <input
          style={{ ...inputStyle, flex: 1, minWidth: 140 }}
          aria-label="판정 사유"
          placeholder="판정 사유 (필수)"
          maxLength={1000}
          value={reason}
          onChange={e => setReason(e.target.value)}
        />
        <button style={buttonStyle(canSubmit)} disabled={!canSubmit} onClick={submit}>
          {confirmed ? '수정' : '확정'}
        </button>
      </div>
      {error && <div style={errorStyle}>{error}</div>}
    </div>
  )
}
