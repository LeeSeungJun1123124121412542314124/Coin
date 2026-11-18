import { useEffect, useState } from 'react'
import { addSymbol, getSymbols, removeSymbol } from '../../lib/learningApi.ts'
import type { Interval, LearningSymbol } from '../../lib/learningApi.ts'
import { Card } from '../shared/Card'
import ErrorState from '../shared/ErrorState'
import { BacktestPanel } from '../learning/BacktestPanel'
import { JournalPanel } from '../learning/JournalPanel'
import { LearningChart } from '../learning/LearningChart'
import { PerformancePanel } from '../learning/PerformancePanel'
import { ReviewPanel } from '../learning/ReviewPanel'
import { TradePanel } from '../learning/TradePanel'
import {
  DIM, MUTED, buttonStyle, errorStyle, errorText, inputStyle, noteStyle, titleStyle, toggleStyle, useLoader,
} from '../learning/learningShared.ts'

type SubTab = 'chart' | 'trade' | 'journal' | 'review' | 'performance' | 'backtest'

const SUB_TABS: [SubTab, string][] = [
  ['chart', '차트'],
  ['trade', '매매'],
  ['journal', '일지'],
  ['review', '복기'],
  ['performance', '성과'],
  ['backtest', '백테스트'],
]

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: '백필 중', color: '#facc15' },
  done: { text: '준비됨', color: '#4ade80' },
  failed: { text: '백필 실패', color: '#f87171' },
}

const BACKFILL_POLL_MS = 3000

// 학습 탭 — 차트로 국면 판단 → 근거와 함께 모의매매 → 일지·복기·성과 → 백테스트
export function Learning() {
  const symbols = useLoader(getSymbols)
  const [chosen, setChosen] = useState<string | null>(null)
  const [tab, setTab] = useState<SubTab>('chart')
  const [chartInterval, setChartInterval] = useState<Interval>('1d')

  const list = symbols.data ?? []
  const selected = list.find(s => s.symbol === chosen) ?? list[0] ?? null

  // 백필 대기 종목이 있으면 주기적으로 목록을 다시 받아 상태 변화를 반영
  const { data: symbolData, reload: reloadSymbols } = symbols
  useEffect(() => {
    if (!symbolData?.some(s => s.backfill_status === 'pending')) return
    const id = setTimeout(reloadSymbols, BACKFILL_POLL_MS)
    return () => clearTimeout(id)
  }, [symbolData, reloadSymbols])

  const needsSymbol = tab === 'chart' || tab === 'trade'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {symbols.error ? (
        <ErrorState error={symbols.error} onRetry={symbols.reload} />
      ) : (
        <SymbolManager
          list={list}
          loading={!symbols.data}
          selected={selected?.symbol ?? null}
          onSelect={setChosen}
          onChanged={reloadSymbols}
        />
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {SUB_TABS.map(([key, label]) => (
          <button key={key} style={toggleStyle(tab === key)} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>

      {needsSymbol && !selected ? (
        symbols.data && <Card><div style={noteStyle}>추적 종목을 먼저 추가하세요 (예: BTCUSDT).</div></Card>
      ) : tab === 'chart' && selected ? (
        <LearningChart
          symbol={selected.symbol}
          interval={chartInterval}
          onIntervalChange={setChartInterval}
          ready={selected.backfill_status !== 'pending'}
        />
      ) : tab === 'trade' && selected ? (
        <TradePanel symbol={selected.symbol} interval={chartInterval} />
      ) : tab === 'journal' ? (
        <JournalPanel />
      ) : tab === 'review' ? (
        <ReviewPanel />
      ) : tab === 'performance' ? (
        <PerformancePanel symbols={list.map(s => s.symbol)} />
      ) : tab === 'backtest' ? (
        <BacktestPanel />
      ) : null}
    </div>
  )
}

// 추적 종목 관리 — 목록(백필 상태)·추가·제거, 선택 종목은 차트·매매 탭에 쓰인다
function SymbolManager({ list, loading, selected, onSelect, onChanged }: {
  list: LearningSymbol[]
  loading: boolean
  selected: string | null
  onSelect: (symbol: string) => void
  onChanged: () => void
}) {
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canAdd = !busy && input.trim() !== ''

  const add = async () => {
    setBusy(true)
    setError(null)
    try {
      const added = await addSymbol(input.trim().toUpperCase())
      setInput('')
      onSelect(added.symbol)
      onChanged()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  // 열린 포지션이 있는 종목은 서버가 400으로 거부 — 메시지 그대로 표시
  const remove = async (symbol: string) => {
    if (!window.confirm(`${symbol} 추적을 해제할까요?`)) return
    setBusy(true)
    setError(null)
    try {
      await removeSymbol(symbol)
      onChanged()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <h3 style={titleStyle}>추적 종목</h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        {loading ? (
          <span style={noteStyle}>불러오는 중...</span>
        ) : list.length === 0 ? (
          <span style={noteStyle}>추적 중인 종목이 없습니다. 바이낸스 USDT 현물 심볼을 추가하세요.</span>
        ) : list.map(s => {
          const status = STATUS_LABELS[s.backfill_status] ?? { text: s.backfill_status, color: MUTED }
          const active = s.symbol === selected
          return (
            <div key={s.symbol} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: active ? '#1e3a5f' : '#0f172a',
              border: `1px solid ${active ? '#60a5fa' : '#334155'}`,
              borderRadius: 8, padding: '4px 6px 4px 10px',
            }}>
              <button
                onClick={() => onSelect(s.symbol)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left' }}
              >
                <span style={{ color: '#e2e8f0', fontWeight: 600, fontSize: '0.85rem' }}>{s.symbol}</span>
                <span style={{ color: status.color, fontSize: '0.72rem', marginLeft: 6 }}>{status.text}</span>
                {s.listed_at && <span style={{ color: DIM, fontSize: '0.7rem', marginLeft: 6 }}>상장 {s.listed_at}</span>}
              </button>
              <button
                aria-label={`${s.symbol} 제거`}
                title="추적 해제"
                disabled={busy}
                onClick={() => remove(s.symbol)}
                style={{ background: 'none', border: 'none', color: DIM, cursor: busy ? 'not-allowed' : 'pointer', fontSize: '0.9rem', padding: '0 4px' }}
              >
                ×
              </button>
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <input
          style={{ ...inputStyle, width: 180 }}
          aria-label="추가할 종목 심볼"
          placeholder="예: BTCUSDT"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && canAdd) add() }}
        />
        <button style={buttonStyle(canAdd)} disabled={!canAdd} onClick={add}>추가</button>
        <span style={{ ...noteStyle, alignSelf: 'center' }}>추가하면 상장일부터 일봉·4시간봉을 백필합니다 (최대 5종목).</span>
      </div>
      {error && <div style={{ ...errorStyle, marginTop: 8 }}>{error}</div>}
    </Card>
  )
}
