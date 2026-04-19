import { useRef, useEffect, useState } from 'react'
import {
  createChart,
  CandlestickSeries as CandlestickDef,
  HistogramSeries as HistogramDef,
} from 'lightweight-charts'
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import { apiFetch } from '../../lib/api'

interface OhlcvPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type Interval = '1d' | '1wk' | '1mo'

const INTERVAL_LABELS: Record<Interval, string> = {
  '1d':  '일',
  '1wk': '주',
  '1mo': '월',
}

export interface KrStockChartProps {
  ticker: string
  name: string
}

export function KrStockChart({ ticker, name }: KrStockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const [interval, setInterval] = useState<Interval>('1d')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // 차트 인스턴스 초기화 (마운트 시 1회)
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0f172a' },
        textColor: '#94a3b8',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#1e293b' },
      leftPriceScale: { visible: false },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 340,
    })

    // 캔들스틱 시리즈
    const candle = chart.addSeries(CandlestickDef, {
      upColor: '#60a5fa',
      downColor: '#f87171',
      borderUpColor: '#60a5fa',
      borderDownColor: '#f87171',
      wickUpColor: '#60a5fa80',
      wickDownColor: '#f8717180',
    })

    // 거래량 (같은 패널, 하단 20%)
    const vol = chart.addSeries(HistogramDef, {
      color: '#334155',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    })

    chartRef.current = chart
    candleRef.current = candle
    volRef.current = vol

    // 컨테이너 크기 변경 대응
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      chart.applyOptions({ width, height })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volRef.current = null
    }
  }, [])

  // 기간/티커 변경 시 데이터 재조회
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)

    apiFetch<OhlcvPoint[]>(`/api/stock-chart/${encodeURIComponent(ticker)}?interval=${interval}`)
      .then(json => {
        if (cancelled || !candleRef.current || !volRef.current) return

        candleRef.current.setData(
          json.map(d => ({
            time: d.date as Time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
          }))
        )

        volRef.current.setData(
          json.map(d => ({
            time: d.date as Time,
            value: d.volume,
            color: d.close >= d.open ? '#1e3a5f' : '#3b1f0d',
          }))
        )

        chartRef.current?.timeScale().fitContent()
        if (!cancelled) setLoading(false)
      })
      .catch(() => {
        if (!cancelled) { setError(true); setLoading(false) }
      })

    return () => { cancelled = true }
  }, [ticker, interval])

  return (
    <div style={{
      background: '#0f172a', width: '100%', height: '100%',
      display: 'flex', flexDirection: 'column',
      boxSizing: 'border-box',
    }}>
      {/* 헤더 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px 8px',
        flexShrink: 0,
      }}>
        <span style={{ color: '#94a3b8', fontSize: '0.85rem', fontWeight: 600 }}>{name}</span>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['1d', '1wk', '1mo'] as Interval[]).map(i => (
            <button key={i} onClick={() => setInterval(i)} style={{
              background: interval === i ? '#334155' : 'transparent',
              color: interval === i ? '#e2e8f0' : '#475569',
              border: '1px solid ' + (interval === i ? '#475569' : '#1e293b'),
              borderRadius: 6, padding: '3px 10px', fontSize: '0.75rem', cursor: 'pointer',
            }}>
              {INTERVAL_LABELS[i]}
            </button>
          ))}
        </div>
      </div>

      {/* 차트 영역 */}
      <div style={{ position: 'relative', flex: 1 }}>
        {/* 로딩 */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#0f172a',
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              border: '3px solid #1e293b', borderTopColor: '#60a5fa',
              animation: 'kr-spin 0.8s linear infinite',
            }} />
            <style>{`@keyframes kr-spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        )}
        {/* 에러 */}
        {!loading && error && (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#94a3b8', fontSize: '0.9rem',
          }}>
            차트를 불러올 수 없습니다
          </div>
        )}
        {/* lightweight-charts 마운트 대상 */}
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      </div>
    </div>
  )
}
