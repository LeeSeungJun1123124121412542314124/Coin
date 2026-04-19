import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { Modal } from '../shared/Modal'
import { SimScorecard } from '../shared/SimScorecard'

// ────────────────────────────────────────
// 타입 정의
// ────────────────────────────────────────

interface SimAccount {
  id: number
  market: 'crypto' | 'kr_stock' | 'us_stock'
  currency: string
  capital: number
  initial_capital: number
  reset_count: number
  roi: number
}

interface SimPrediction {
  id: number
  asset_symbol: string
  mode: 'direction' | 'target_price' | 'portfolio'
  direction: 'long' | 'short' | null
  entry_price: number
  expiry_time: string
  indicator_tags: string[]
  leverage?: number
  status: string
}

interface StockSuggestion {
  ticker: string
  name: string
}

type MarketTab = 'crypto' | 'kr_stock' | 'us_stock'

// ────────────────────────────────────────
// 상수
// ────────────────────────────────────────

const MARKET_LABELS: Record<MarketTab, string> = {
  crypto: '코인 (USDT)',
  kr_stock: '한국주식 (KRW)',
  us_stock: '미국주식 (USD)',
}

const INDICATOR_OPTIONS = ['OI', 'FR', 'F&G', '알트시즌', 'VIX', 'DXY', 'US10Y', '금', '은']

const MODE_LABELS: Record<string, string> = {
  direction: '방향성',
  target_price: '목표가',
  portfolio: '포트폴리오',
}

// ────────────────────────────────────────
// 포맷 헬퍼
// ────────────────────────────────────────

function formatCapital(capital: number, currency: string): string {
  if (currency === 'KRW') {
    return capital.toLocaleString('ko-KR') + ' 원'
  }
  return capital.toFixed(2) + ' ' + currency
}

function formatRoi(roi: number): string {
  const sign = roi >= 0 ? '+' : ''
  return sign + roi.toFixed(1) + '%'
}

function formatDateOnly(isoStr: string): string {
  return isoStr.slice(0, 10)
}

// ────────────────────────────────────────
// 새 예측 모달 내부 폼
// ────────────────────────────────────────

interface NewPredictionFormProps {
  market: MarketTab
  onSubmit: () => void
  onClose: () => void
}

function NewPredictionForm({ market, onSubmit, onClose }: NewPredictionFormProps) {
  const [mode, setMode] = useState<'direction' | 'target_price' | 'portfolio'>('direction')
  const [assetSymbol, setAssetSymbol] = useState('')
  const [direction, setDirection] = useState<'long' | 'short'>('long')
  const [entryPrice, setEntryPrice] = useState('')
  const [entryTime, setEntryTime] = useState('')
  const [expiryTime, setExpiryTime] = useState('')
  const [targetPrice, setTargetPrice] = useState('')
  const [quantity, setQuantity] = useState('')
  const [leverage, setLeverage] = useState(1)
  const [instrumentType, setInstrumentType] = useState<'spot' | 'futures'>('spot')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [indicators, setIndicators] = useState<string[]>([])
  const [note, setNote] = useState('')

  // 주식 검색
  const [searchQuery, setSearchQuery] = useState('')
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const stockMarket: 'kr' | 'us' = market === 'kr_stock' ? 'kr' : 'us'
  const isCrypto = market === 'crypto'

  const handleSearch = async () => {
    const q = searchQuery.trim()
    if (!q) {
      setSearchError('검색어를 입력해주세요.')
      return
    }
    setSearchLoading(true)
    setSearchError(null)
    setShowDropdown(false)
    try {
      const results: StockSuggestion[] = await apiFetch(
        `/api/stock-search?q=${encodeURIComponent(q)}&market=${stockMarket}`
      )
      setSuggestions(results)
      setShowDropdown(true)
    } catch {
      setSearchError('검색 실패')
    } finally {
      setSearchLoading(false)
    }
  }

  const handleSelectSuggestion = (s: StockSuggestion) => {
    if (blurTimer.current) clearTimeout(blurTimer.current)
    setAssetSymbol(s.ticker)
    setSearchQuery(s.ticker)
    setShowDropdown(false)
    setSuggestions([])
  }

  const toggleIndicator = (tag: string) => {
    setIndicators(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    )
  }

  const handleSubmit = async () => {
    if (!assetSymbol.trim()) {
      setSubmitError('자산 심볼을 입력해주세요.')
      return
    }
    if (!entryPrice) {
      setSubmitError('진입 가격을 입력해주세요.')
      return
    }
    if (!entryTime) {
      setSubmitError('진입 시간을 입력해주세요.')
      return
    }
    if (!expiryTime) {
      setSubmitError('만료 시간을 입력해주세요.')
      return
    }

    // datetime-local 값을 ISO 형식으로 변환 (초 단위 없으면 ':00' 추가)
    const toISOWithSeconds = (dt: string) => dt.length === 16 ? dt + ':00' : dt

    const body: Record<string, unknown> = {
      market,
      asset_symbol: assetSymbol.trim(),
      mode,
      entry_price: parseFloat(entryPrice),
      entry_time: toISOWithSeconds(entryTime),
      expiry_time: toISOWithSeconds(expiryTime),
      indicator_tags: indicators,
      note: note || null,
    }

    if (mode === 'direction' || mode === 'portfolio') {
      body.direction = direction
    }

    if (mode === 'target_price') {
      body.target_price = targetPrice ? parseFloat(targetPrice) : null
    }

    if (mode === 'portfolio') {
      body.instrument_type = instrumentType
      body.quantity = quantity ? parseFloat(quantity) : null
      body.leverage = leverage
      body.stop_loss = stopLoss ? parseFloat(stopLoss) : null
      body.take_profit = takeProfit ? parseFloat(takeProfit) : null
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      await apiFetch('/api/sim/predictions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      onSubmit()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '등록 실패'
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    background: '#0f1117',
    border: '1px solid #1e293b',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: '0.875rem',
    padding: '6px 10px',
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    color: '#94a3b8',
    fontSize: '0.75rem',
    marginBottom: 4,
    display: 'block',
  }

  const fieldWrap: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    marginBottom: 14,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 모달 헤더 */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid #1e293b',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <h2 style={{ margin: 0, fontSize: '1rem', color: '#e2e8f0' }}>새 예측 등록</h2>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.2rem', cursor: 'pointer', lineHeight: 1 }}
        >
          ✕
        </button>
      </div>

      {/* 스크롤 가능한 폼 영역 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>

        {/* 모드 선택 */}
        <div style={fieldWrap}>
          <label style={labelStyle}>모드</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['direction', 'target_price', 'portfolio'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 6,
                  border: '1px solid #1e293b',
                  background: mode === m ? '#2563eb' : '#0f1117',
                  color: mode === m ? '#fff' : '#94a3b8',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
        </div>

        {/* 자산 검색 */}
        <div style={{ ...fieldWrap, position: 'relative' }}>
          <label style={labelStyle}>
            {isCrypto ? '심볼 (예: BTCUSDT)' : '종목 검색'}
          </label>
          {isCrypto ? (
            <input
              type="text"
              placeholder="BTCUSDT"
              value={assetSymbol}
              onChange={e => setAssetSymbol(e.target.value)}
              style={inputStyle}
            />
          ) : (
            <>
              <div style={{ display: 'flex', gap: 6 }}>
                <input
                  type="text"
                  placeholder="티커 또는 종목명"
                  value={searchQuery}
                  onChange={e => {
                    setSearchQuery(e.target.value)
                    setAssetSymbol('')
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleSearch()
                    if (e.key === 'Escape') setShowDropdown(false)
                  }}
                  onBlur={() => {
                    blurTimer.current = setTimeout(() => setShowDropdown(false), 150)
                  }}
                  style={{ ...inputStyle, flex: 1, width: 'auto' }}
                />
                <button
                  onClick={handleSearch}
                  disabled={searchLoading}
                  style={{
                    background: 'transparent',
                    border: '1px solid #60a5fa',
                    borderRadius: 6,
                    color: '#60a5fa',
                    cursor: searchLoading ? 'not-allowed' : 'pointer',
                    fontSize: '0.875rem',
                    padding: '6px 12px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {searchLoading ? '검색 중...' : '검색'}
                </button>
              </div>
              {showDropdown && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  zIndex: 100,
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 6,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                  overflow: 'hidden',
                  maxHeight: 200,
                  overflowY: 'auto',
                }}>
                  {suggestions.length === 0 ? (
                    <div style={{ padding: '8px 12px', color: '#94a3b8', fontSize: '0.8rem' }}>
                      검색 결과 없음
                    </div>
                  ) : (
                    suggestions.map(s => (
                      <div
                        key={s.ticker}
                        onMouseDown={() => handleSelectSuggestion(s)}
                        style={{
                          padding: '8px 12px',
                          cursor: 'pointer',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: 8,
                          borderBottom: '1px solid #1e293b',
                          background: '#0f172a',
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = '#1e3a5f')}
                        onMouseLeave={e => (e.currentTarget.style.background = '#0f172a')}
                      >
                        <span style={{ color: '#60a5fa', fontSize: '0.85rem', fontWeight: 600 }}>{s.ticker}</span>
                        <span style={{ color: '#94a3b8', fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
              {searchError && (
                <div style={{ color: '#f87171', fontSize: '0.75rem' }}>{searchError}</div>
              )}
              {assetSymbol && (
                <div style={{ color: '#4ade80', fontSize: '0.75rem' }}>선택됨: {assetSymbol}</div>
              )}
            </>
          )}
        </div>

        {/* 방향 (direction, portfolio 모드) */}
        {(mode === 'direction' || mode === 'portfolio') && (
          <div style={fieldWrap}>
            <label style={labelStyle}>방향</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setDirection('long')}
                style={{
                  padding: '6px 20px',
                  borderRadius: 6,
                  border: '1px solid #1e293b',
                  background: direction === 'long' ? '#16a34a' : '#0f1117',
                  color: direction === 'long' ? '#fff' : '#94a3b8',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: direction === 'long' ? 600 : 400,
                }}
              >
                롱
              </button>
              <button
                onClick={() => setDirection('short')}
                style={{
                  padding: '6px 20px',
                  borderRadius: 6,
                  border: '1px solid #1e293b',
                  background: direction === 'short' ? '#dc2626' : '#0f1117',
                  color: direction === 'short' ? '#fff' : '#94a3b8',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: direction === 'short' ? 600 : 400,
                }}
              >
                숏
              </button>
            </div>
          </div>
        )}

        {/* 진입 가격 */}
        <div style={fieldWrap}>
          <label style={labelStyle}>진입 가격</label>
          <input
            type="number"
            placeholder="0.00"
            value={entryPrice}
            onChange={e => setEntryPrice(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* 진입 시간 */}
        <div style={fieldWrap}>
          <label style={labelStyle}>진입 시간</label>
          <input
            type="datetime-local"
            value={entryTime}
            onChange={e => setEntryTime(e.target.value)}
            style={{
              ...inputStyle,
              colorScheme: 'dark',
            }}
          />
        </div>

        {/* 만료 시간 */}
        <div style={fieldWrap}>
          <label style={labelStyle}>만료 시간</label>
          <input
            type="datetime-local"
            value={expiryTime}
            onChange={e => setExpiryTime(e.target.value)}
            style={{
              ...inputStyle,
              colorScheme: 'dark',
            }}
          />
        </div>

        {/* 목표가 (target_price 모드) */}
        {mode === 'target_price' && (
          <div style={fieldWrap}>
            <label style={labelStyle}>목표 가격</label>
            <input
              type="number"
              placeholder="0.00"
              value={targetPrice}
              onChange={e => setTargetPrice(e.target.value)}
              style={inputStyle}
            />
          </div>
        )}

        {/* 포트폴리오 전용 필드 */}
        {mode === 'portfolio' && (
          <>
            {/* 종목 유형 */}
            <div style={fieldWrap}>
              <label style={labelStyle}>종목 유형</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {(['spot', 'futures'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => setInstrumentType(t)}
                    style={{
                      padding: '6px 20px',
                      borderRadius: 6,
                      border: '1px solid #1e293b',
                      background: instrumentType === t ? '#2563eb' : '#0f1117',
                      color: instrumentType === t ? '#fff' : '#94a3b8',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: instrumentType === t ? 600 : 400,
                    }}
                  >
                    {t === 'spot' ? '현물' : '선물'}
                  </button>
                ))}
              </div>
            </div>

            <div style={fieldWrap}>
              <label style={labelStyle}>수량</label>
              <input
                type="number"
                placeholder="0"
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={fieldWrap}>
              <label style={labelStyle}>레버리지: {leverage}x</label>
              <input
                type="range"
                min={1}
                max={64}
                value={leverage}
                onChange={e => setLeverage(parseInt(e.target.value))}
                style={{ width: '100%', accentColor: '#60a5fa' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#94a3b8', fontSize: '0.7rem' }}>
                <span>1x</span>
                <span>64x</span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label style={labelStyle}>손절가 (선택)</label>
                <input
                  type="number"
                  placeholder="0.00"
                  value={stopLoss}
                  onChange={e => setStopLoss(e.target.value)}
                  style={inputStyle}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label style={labelStyle}>익절가 (선택)</label>
                <input
                  type="number"
                  placeholder="0.00"
                  value={takeProfit}
                  onChange={e => setTakeProfit(e.target.value)}
                  style={inputStyle}
                />
              </div>
            </div>
          </>
        )}

        {/* 인디케이터 태그 */}
        <div style={fieldWrap}>
          <label style={labelStyle}>인디케이터 참고</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {INDICATOR_OPTIONS.map(tag => (
              <label
                key={tag}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  cursor: 'pointer',
                  color: indicators.includes(tag) ? '#60a5fa' : '#94a3b8',
                  fontSize: '0.8rem',
                }}
              >
                <input
                  type="checkbox"
                  checked={indicators.includes(tag)}
                  onChange={() => toggleIndicator(tag)}
                  style={{ accentColor: '#60a5fa' }}
                />
                {tag}
              </label>
            ))}
          </div>
        </div>

        {/* 메모 */}
        <div style={fieldWrap}>
          <label style={labelStyle}>메모 (선택)</label>
          <input
            type="text"
            placeholder="간단한 메모..."
            value={note}
            onChange={e => setNote(e.target.value)}
            style={inputStyle}
          />
        </div>

        {submitError && (
          <div style={{ color: '#f87171', fontSize: '0.8rem', marginBottom: 12 }}>
            {submitError}
          </div>
        )}
      </div>

      {/* 하단 버튼 */}
      <div style={{
        padding: '14px 20px',
        borderTop: '1px solid #1e293b',
        display: 'flex',
        justifyContent: 'flex-end',
        gap: 10,
        flexShrink: 0,
      }}>
        <button
          onClick={onClose}
          style={{
            padding: '8px 20px',
            borderRadius: 6,
            border: '1px solid #1e293b',
            background: 'transparent',
            color: '#94a3b8',
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          취소
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{
            padding: '8px 20px',
            borderRadius: 6,
            border: 'none',
            background: submitting ? '#1e3a5f' : '#2563eb',
            color: '#fff',
            cursor: submitting ? 'not-allowed' : 'pointer',
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {submitting ? '등록 중...' : '등록'}
        </button>
      </div>
    </div>
  )
}

// ────────────────────────────────────────
// 메인 시뮬레이터 컴포넌트
// ────────────────────────────────────────

export function Simulator() {
  const [activeMarket, setActiveMarket] = useState<MarketTab>('crypto')
  const [accounts, setAccounts] = useState<SimAccount[]>([])
  const [accountsLoading, setAccountsLoading] = useState(true)
  const [accountsError, setAccountsError] = useState<string | null>(null)

  const [predictions, setPredictions] = useState<SimPrediction[]>([])
  const [predictionsLoading, setPredictionsLoading] = useState(true)
  const [predictionsError, setPredictionsError] = useState<string | null>(null)

  const [showNewPrediction, setShowNewPrediction] = useState(false)

  // 계좌 목록 조회
  const fetchAccounts = useCallback(async () => {
    setAccountsLoading(true)
    setAccountsError(null)
    try {
      const data: SimAccount[] = await apiFetch('/api/sim/accounts')
      setAccounts(data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '계좌 조회 실패'
      setAccountsError(msg)
    } finally {
      setAccountsLoading(false)
    }
  }, [])

  // 예측 목록 조회
  const fetchPredictions = useCallback(async () => {
    setPredictionsLoading(true)
    setPredictionsError(null)
    try {
      const data: SimPrediction[] = await apiFetch(
        `/api/sim/predictions?market=${activeMarket}&status=pending`
      )
      setPredictions(data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '예측 조회 실패'
      setPredictionsError(msg)
    } finally {
      setPredictionsLoading(false)
    }
  }, [activeMarket])

  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

  useEffect(() => {
    fetchPredictions()
  }, [fetchPredictions])

  // 현재 마켓의 계좌
  const currentAccount = accounts.find(a => a.market === activeMarket) ?? null

  // 예측 취소
  const handleCancelPrediction = async (id: number) => {
    try {
      await apiFetch(`/api/sim/predictions/${id}`, { method: 'DELETE' })
      await fetchPredictions()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '취소 실패'
      alert(msg)
    }
  }

  // 계좌 리셋
  const handleResetAccount = async () => {
    if (!currentAccount) return
    const confirmed = window.confirm(
      '계좌 자본금을 리셋합니다. 기존 예측은 유지됩니다.'
    )
    if (!confirmed) return

    const input = window.prompt('새 초기 자본금을 입력하세요. (숫자만)')
    if (input === null) return
    const newCapital = parseFloat(input)
    if (isNaN(newCapital) || newCapital <= 0) {
      alert('올바른 금액을 입력해주세요.')
      return
    }

    try {
      await apiFetch(`/api/sim/accounts/${activeMarket}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_capital: newCapital }),
      })
      await fetchAccounts()
      await fetchPredictions()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '리셋 실패'
      alert(msg)
    }
  }

  // 예측 등록 완료
  const handlePredictionSubmitted = () => {
    setShowNewPrediction(false)
    fetchPredictions()
  }

  const dividerStyle: React.CSSProperties = {
    borderBottom: '1px solid #1e293b',
    marginBottom: 16,
  }

  return (
    <div style={{ color: '#e2e8f0' }}>
      <h1 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 20, color: '#e2e8f0' }}>
        시뮬레이터
      </h1>

      {/* ── 마켓 탭 ── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {(['crypto', 'kr_stock', 'us_stock'] as const).map(market => (
          <button
            key={market}
            onClick={() => setActiveMarket(market)}
            style={{
              padding: '8px 18px',
              borderRadius: 8,
              border: '1px solid #1e293b',
              background: activeMarket === market ? '#2563eb' : '#0f172a',
              color: activeMarket === market ? '#fff' : '#94a3b8',
              cursor: 'pointer',
              fontSize: '0.875rem',
              fontWeight: activeMarket === market ? 600 : 400,
              transition: 'all 0.15s',
            }}
          >
            {MARKET_LABELS[market]}
          </button>
        ))}
      </div>

      {/* ── 계좌 요약 ── */}
      <div style={{
        background: '#0f172a',
        border: '1px solid #1e293b',
        borderRadius: 10,
        padding: '16px 20px',
        marginBottom: 20,
      }}>
        {accountsLoading ? (
          <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>로딩 중...</div>
        ) : accountsError ? (
          <div style={{ color: '#f87171', fontSize: '0.875rem' }}>{accountsError}</div>
        ) : currentAccount ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 24 }}>
            <div>
              <div style={{ color: '#94a3b8', fontSize: '0.7rem', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>잔고</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#e2e8f0' }}>
                {formatCapital(currentAccount.capital, currentAccount.currency)}
              </div>
            </div>
            <div>
              <div style={{ color: '#94a3b8', fontSize: '0.7rem', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>ROI</div>
              <div style={{
                fontSize: '1.1rem',
                fontWeight: 700,
                color: currentAccount.roi >= 0 ? '#4ade80' : '#f87171',
              }}>
                {formatRoi(currentAccount.roi)}
              </div>
            </div>
            <div>
              <div style={{ color: '#94a3b8', fontSize: '0.7rem', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>초기 자본</div>
              <div style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
                {formatCapital(currentAccount.initial_capital, currentAccount.currency)}
              </div>
            </div>
            <div>
              <div style={{ color: '#94a3b8', fontSize: '0.7rem', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>리셋 횟수</div>
              <div style={{ fontSize: '0.9rem', color: '#94a3b8' }}>{currentAccount.reset_count}회</div>
            </div>
          </div>
        ) : (
          <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>계좌 정보 없음</div>
        )}
      </div>

      {/* ── 액션 버튼 ── */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, ...dividerStyle, paddingBottom: 20 }}>
        <button
          onClick={() => setShowNewPrediction(true)}
          style={{
            padding: '9px 18px',
            borderRadius: 8,
            border: 'none',
            background: '#2563eb',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          + 새 예측
        </button>
        <button
          onClick={handleResetAccount}
          style={{
            padding: '9px 18px',
            borderRadius: 8,
            border: '1px solid #1e293b',
            background: 'transparent',
            color: '#f87171',
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          계좌 리셋
        </button>
      </div>

      {/* ── 활성 예측 목록 ── */}
      <div>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#e2e8f0', marginBottom: 12 }}>
          활성 예측
        </h2>

        {predictionsLoading ? (
          <div style={{ color: '#94a3b8', fontSize: '0.875rem', padding: '20px 0' }}>로딩 중...</div>
        ) : predictionsError ? (
          <div style={{ color: '#f87171', fontSize: '0.875rem', padding: '20px 0' }}>{predictionsError}</div>
        ) : predictions.length === 0 ? (
          <div style={{
            background: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: 10,
            padding: '32px',
            textAlign: 'center',
            color: '#94a3b8',
            fontSize: '0.875rem',
          }}>
            활성 예측이 없습니다. '+ 새 예측' 버튼으로 예측을 등록하세요.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {predictions.map(pred => (
              <div
                key={pred.id}
                style={{
                  background: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: 10,
                  padding: '14px 18px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  flexWrap: 'wrap',
                }}
              >
                {/* 심볼 */}
                <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#e2e8f0', minWidth: 100 }}>
                  {pred.asset_symbol}
                </div>

                {/* 방향 */}
                {pred.direction && (
                  <div style={{
                    padding: '2px 10px',
                    borderRadius: 4,
                    background: pred.direction === 'long' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
                    color: pred.direction === 'long' ? '#4ade80' : '#f87171',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}>
                    {pred.direction === 'long' ? '롱' : '숏'}
                  </div>
                )}

                {/* 모드 */}
                <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                  {MODE_LABELS[pred.mode]}
                </div>

                {/* 레버리지 (포트폴리오 모드이고 leverage > 1인 경우) */}
                {pred.mode === 'portfolio' && pred.leverage && pred.leverage > 1 && (
                  <div style={{ color: '#60a5fa', fontSize: '0.8rem', fontWeight: 600 }}>
                    x{pred.leverage}
                  </div>
                )}

                {/* 진입가 */}
                <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                  진입: <span style={{ color: '#e2e8f0' }}>{pred.entry_price.toLocaleString()}</span>
                </div>

                {/* 만료일 */}
                <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                  만료: <span style={{ color: '#e2e8f0' }}>{formatDateOnly(pred.expiry_time)}</span>
                </div>

                {/* 인디케이터 태그 */}
                {pred.indicator_tags && pred.indicator_tags.length > 0 && (
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {pred.indicator_tags.map(tag => (
                      <span
                        key={tag}
                        style={{
                          padding: '1px 6px',
                          borderRadius: 3,
                          background: '#1e293b',
                          color: '#94a3b8',
                          fontSize: '0.7rem',
                        }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* 취소 버튼 */}
                <button
                  onClick={() => handleCancelPrediction(pred.id)}
                  style={{
                    marginLeft: 'auto',
                    padding: '5px 14px',
                    borderRadius: 6,
                    border: '1px solid #f87171',
                    background: 'transparent',
                    color: '#f87171',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    flexShrink: 0,
                  }}
                >
                  취소
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 스코어카드 ── */}
      <SimScorecard market={activeMarket} />

      {/* ── 새 예측 모달 ── */}
      <Modal open={showNewPrediction} onClose={() => setShowNewPrediction(false)}>
        <NewPredictionForm
          market={activeMarket}
          onSubmit={handlePredictionSubmitted}
          onClose={() => setShowNewPrediction(false)}
        />
      </Modal>
    </div>
  )
}
