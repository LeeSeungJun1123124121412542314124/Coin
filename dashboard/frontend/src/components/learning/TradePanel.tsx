import { useCallback, useState } from 'react'
import { getAccount, getOrderContext, postOrder } from '../../lib/learningApi.ts'
import type { AccountResponse, IchimokuState, Interval, OrderBody, OrderContext, Phase } from '../../lib/learningApi.ts'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import { SkeletonCard } from '../shared/Skeleton'
import { PHASE_LABELS, formatUsdtKrw } from './learningChartData.ts'
import {
  DIM, ICHIMOKU_FIELDS, INTERVAL_LABELS, MUTED, UNDECIDABLE, buttonStyle, errorStyle, errorText, fmtBarTime, fmtPrice,
  fmtQty, inputStyle, isIntraday, noteStyle, pnlArrow, pnlColor, segButtonStyle, segGroupStyle, tdStyle, thStyle, titleStyle, useLoader,
} from './learningShared.ts'

const PHASES = Object.keys(PHASE_LABELS) as Phase[]

interface TradePanelProps {
  symbol: string
  // 근거 미리 채우기·감지 기록에 쓰는 봉 (차트의 봉 전환을 따른다)
  interval: Interval
}

export function TradePanel({ symbol, interval }: TradePanelProps) {
  const account = useLoader(getAccount)
  const loadContext = useCallback(() => getOrderContext(symbol, interval), [symbol, interval])
  const context = useLoader(loadContext)
  const held = account.data?.positions.find(p => p.symbol === symbol)?.qty ?? 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {account.error ? (
        <ErrorState error={account.error} onRetry={account.reload} />
      ) : account.data ? (
        <AccountCard account={account.data} />
      ) : (
        <SkeletonCard />
      )}

      {context.error ? (
        <ErrorState error={context.error} onRetry={context.reload} />
      ) : context.data ? (
        <OrderForm
          key={`${symbol}-${interval}`}
          symbol={symbol}
          interval={interval}
          context={context.data}
          held={held}
          cash={account.data?.cash_usdt ?? 0}
          onFilled={account.reload}
        />
      ) : (
        <SkeletonCard height={240} />
      )}
    </div>
  )
}

function AccountCard({ account }: { account: AccountResponse }) {
  // 환율 조회 실패(null)면 원화 생략
  const rate = account.usd_krw
  return (
    <Card>
      <h3 style={titleStyle}>모의 계좌</h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, fontSize: '0.85rem', color: MUTED, marginBottom: 12 }}>
        <div><span style={{ color: DIM }}>현금 </span>{formatUsdtKrw(account.cash_usdt, rate)}</div>
        <div>
          <span style={{ color: DIM }}>평가 자산 </span>
          {account.equity_usdt === null ? '현재가를 가져오지 못해 계산할 수 없습니다' : formatUsdtKrw(account.equity_usdt, rate)}
        </div>
        <div><span style={{ color: DIM }}>시작 자금 </span>{formatUsdtKrw(account.initial_usdt, rate)}</div>
      </div>
      {account.positions.length === 0 ? (
        <div style={noteStyle}>보유 포지션이 없습니다.</div>
      ) : (
        <div className="table-scroll">
          <table style={{ width: '100%', minWidth: 480, borderCollapse: 'collapse', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
            <thead>
              <tr style={{ color: DIM, textAlign: 'right', borderBottom: '1px solid var(--line)' }}>
                <th style={{ ...thStyle, textAlign: 'left' }}>종목</th>
                <th style={thStyle}>수량</th>
                <th style={thStyle}>평균 단가</th>
                <th style={thStyle}>평가액</th>
                <th style={thStyle}>평가 손익</th>
              </tr>
            </thead>
            <tbody>
              {account.positions.map(p => (
                <tr key={p.symbol} style={{ textAlign: 'right', borderBottom: '1px solid var(--line)' }}>
                  <td style={{ ...tdStyle, textAlign: 'left', color: 'var(--text)', fontWeight: 600 }}>{p.symbol}</td>
                  <td style={tdStyle}>{fmtQty(p.qty)}</td>
                  <td style={tdStyle}>{fmtPrice(p.avg_cost)}</td>
                  <td style={tdStyle}>{p.market_value === null ? '—' : formatUsdtKrw(p.market_value, rate)}</td>
                  <td style={{ ...tdStyle, color: pnlColor(p.unrealized_pnl) }}>
                    {p.unrealized_pnl === null ? '—' : `${pnlArrow(p.unrealized_pnl)}${p.unrealized_pnl.toFixed(2)} USDT`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

interface OrderFormProps {
  symbol: string
  interval: Interval
  context: OrderContext
  held: number
  cash: number
  onFilled: () => void
}

// 근거 입력 + 주문. 국면은 기본값 없이 직접 골라야 하고, 일목 4항목은 감지값으로 미리 채운다
function OrderForm({ symbol, interval, context, held, cash, onFilled }: OrderFormProps) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [phase, setPhase] = useState<Phase | ''>('')
  const [ichimoku, setIchimoku] = useState<IchimokuState>(context.ichimoku_state)
  const [memo, setMemo] = useState('')
  const [buyAmount, setBuyAmount] = useState('')
  const [sellQty, setSellQty] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)

  const withHour = isIntraday(interval)
  const canBuy = phase !== '' && !busy && Number(buyAmount) > 0
  const canSell = phase !== '' && !busy && Number(sellQty) > 0

  const submit = async (side: 'buy' | 'sell') => {
    if (phase === '') return
    setBusy(true)
    setResult(null)
    const body: OrderBody = {
      symbol,
      side,
      interval,
      rationale: { phase, ichimoku, ...(memo.trim() ? { memo: memo.trim() } : {}) },
      ...(side === 'buy' ? { usdt_amount: Number(buyAmount) } : { qty: Number(sellQty) }),
    }
    try {
      const r = await postOrder(body)
      setResult({
        ok: true,
        text: `${side === 'buy' ? '매수' : '매도'} 체결 — 수량 ${fmtQty(r.qty)} · 가격 ${fmtPrice(r.price)} · 수수료 ${r.fee_usdt.toFixed(2)} USDT · 남은 현금 ${formatUsdtKrw(r.cash_usdt, null)}`,
      })
      setBuyAmount('')
      setSellQty('')
      onFilled()
    } catch (e) {
      setResult({ ok: false, text: errorText(e) })
    } finally {
      setBusy(false)
    }
  }

  const labelStyle = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.75rem', color: MUTED } as const

  const isBuy = side === 'buy'
  const amount = isBuy ? buyAmount : sellQty
  const setAmount = isBuy ? setBuyAmount : setSellQty
  const canSubmit = isBuy ? canBuy : canSell
  const unit = isBuy ? 'USDT' : symbol.replace(/USDT$/, '')
  // 빠른 비율 — 매수는 보유 현금, 매도는 보유 수량 기준. 100%는 표시값 반올림 없이 원본 값을 쓴다
  const quickFill = (pct: number) => {
    if (isBuy) setBuyAmount(pct === 1 ? String(cash) : String(Math.floor(cash * pct * 100) / 100))
    else setSellQty(pct === 1 ? String(held) : String(Math.floor(held * pct * 1e8) / 1e8))
  }

  return (
    <Card>
      <h3 style={titleStyle}>{symbol} 모의 주문</h3>
      <div style={{ ...noteStyle, marginBottom: 12 }}>
        근거 기준: {INTERVAL_LABELS[interval]} (차트의 봉 전환을 따릅니다). 주문 전에 국면을 직접 판단해 고르세요.
      </div>

      <div className="tap-seg" style={{ ...segGroupStyle, display: 'flex', marginBottom: 12 }} role="group" aria-label="주문 방향">
        {([['buy', '매수', 'var(--up)'], ['sell', '매도', 'var(--down)']] as const).map(([key, label, tone]) => (
          <button
            key={key}
            style={{ ...segButtonStyle(side === key, tone), flex: 1 }}
            aria-pressed={side === key}
            onClick={() => setSide(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ ...labelStyle, marginBottom: 10 }}>
        {isBuy ? `매수 금액 (보유 현금 ${fmtPrice(cash)} USDT)` : `매도 수량 (보유 ${fmtQty(held)})`}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            style={{ ...inputStyle, flex: 1, minWidth: 0, fontFamily: 'var(--font-mono)' }}
            aria-label={isBuy ? '매수 금액 (USDT)' : '매도 수량'}
            type="number" min="0" step="any" value={amount}
            onChange={e => setAmount(e.target.value)}
          />
          <span style={{ color: DIM, fontSize: '0.8rem' }}>{unit}</span>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {[0.25, 0.5, 0.75, 1].map(pct => {
          const enabled = !busy && (isBuy ? cash > 0 : held > 0)
          return (
            <button
              key={pct}
              style={{ ...buttonStyle(enabled), flex: 1, background: 'var(--seg-active)', color: enabled ? 'var(--text)' : DIM }}
              disabled={!enabled}
              onClick={() => quickFill(pct)}
            >
              {pct === 1 ? '전량' : `${pct * 100}%`}
            </button>
          )
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, marginBottom: 12 }}>
        <label style={labelStyle}>
          와이코프 국면 (필수)
          <select style={inputStyle} value={phase} onChange={e => setPhase(e.target.value as Phase | '')}>
            <option value="">국면 선택</option>
            {PHASES.map(p => <option key={p} value={p}>{PHASE_LABELS[p]}</option>)}
          </select>
        </label>
        {ICHIMOKU_FIELDS.map(f => (
          <label key={f.key} style={labelStyle}>
            일목 {f.label}
            <select
              style={inputStyle}
              value={ichimoku[f.key] ?? ''}
              onChange={e => setIchimoku(s => ({ ...s, [f.key]: e.target.value === '' ? null : e.target.value }))}
            >
              {Object.entries(f.options).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              <option value="">{UNDECIDABLE}</option>
            </select>
          </label>
        ))}
      </div>

      <DetectedInfo context={context} withHour={withHour} />

      <label style={{ ...labelStyle, marginBottom: 12 }}>
        근거 메모 (선택)
        <textarea
          style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
          maxLength={2000}
          value={memo}
          onChange={e => setMemo(e.target.value)}
          placeholder="판단 근거를 자유롭게 적어 두세요"
        />
      </label>

      <div style={{ ...noteStyle, marginBottom: 10 }}>수수료 0.1% (체결 시 차감, 결과에 표시)</div>
      <button
        style={{
          ...buttonStyle(canSubmit),
          width: '100%', height: 40,
          ...(canSubmit ? { background: isBuy ? 'var(--up)' : 'var(--down)', color: 'var(--bg)' } : {}),
        }}
        disabled={!canSubmit}
        onClick={() => submit(side)}
      >
        {isBuy ? '매수 주문' : '매도 주문'}
      </button>
      {phase === '' && <div style={{ ...noteStyle, marginTop: 8 }}>국면을 선택해야 주문할 수 있습니다.</div>}
      {result && <div style={{ ...(result.ok ? noteStyle : errorStyle), marginTop: 8 }}>{result.text}</div>}
    </Card>
  )
}

// 감지된 와이코프 후보(최근 5봉)·현재 박스 — 읽기 전용
function DetectedInfo({ context, withHour }: { context: OrderContext; withHour: boolean }) {
  const box = context.current_box
  return (
    <div style={{ background: 'var(--bg-inset)', borderRadius: 8, padding: '8px 12px', marginBottom: 12, fontSize: '0.8rem', color: MUTED }}>
      <div style={{ color: DIM, marginBottom: 4 }}>감지된 와이코프 (참고용, 수정 불가)</div>
      <div>
        최근 5봉 후보:{' '}
        {context.wyckoff_recent.length === 0
          ? '없음'
          : context.wyckoff_recent.map(c => (
            `${fmtBarTime(c.time, withHour)} ${c.strong ? '강 ' : ''}${c.type === 'spring' ? '스프링' : '업스러스트'}`
          )).join(', ')}
      </div>
      <div>
        현재 박스:{' '}
        {box
          ? `고점 ${fmtPrice(box.high)} · 저점 ${fmtPrice(box.low)} (${fmtBarTime(box.start, withHour)} ~ ${fmtBarTime(box.end, withHour)})`
          : '없음'}
      </div>
    </div>
  )
}
