import { useEffect, useRef, useState } from 'react'

declare global {
  interface Window {
    TradingView: any
  }
}

interface TradingViewChartProps {
  symbol: string
}

type LoadState = 'loading' | 'ready' | 'error'

const TV_SCRIPT_SRC = 'https://s3.tradingview.com/tv.js'
const CONTAINER_ID = 'tradingview-chart-container'

function loadTvScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.TradingView) {
      resolve()
      return
    }
    if (document.querySelector(`script[src="${TV_SCRIPT_SRC}"]`)) {
      // 이미 주입됐지만 아직 로드 중 — 폴링으로 대기
      const poll = setInterval(() => {
        if (window.TradingView) {
          clearInterval(poll)
          resolve()
        }
      }, 100)
      return
    }
    const script = document.createElement('script')
    script.src = TV_SCRIPT_SRC
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('tv.js 로드 실패'))
    document.head.appendChild(script)
  })
}

export function TradingViewChart({ symbol }: TradingViewChartProps) {
  const [state, setState] = useState<LoadState>('loading')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setState('loading')
    let cancelled = false

    loadTvScript()
      .then(() => {
        if (cancelled || !containerRef.current) return
        containerRef.current.innerHTML = ''
        new window.TradingView.widget({
          container_id: CONTAINER_ID,
          symbol,
          interval: '240',
          style: '1',
          theme: 'dark',
          locale: 'kr',
          timezone: 'Asia/Seoul',
          autosize: true,
          allow_symbol_change: true,
          hide_side_toolbar: false,
          studies: [
            'Volume@tv-basicstudies',
            'RSI@tv-basicstudies',
            'StochasticRSI@tv-basicstudies',
            'MACD@tv-basicstudies',
          ],
        })
        if (!cancelled) setState('ready')
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })

    return () => {
      cancelled = true
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [symbol])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {state === 'loading' && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#0f172a',
          zIndex: 1,
        }}>
          <div style={{
            width: 40, height: 40,
            borderRadius: '50%',
            border: '3px solid #1e293b',
            borderTopColor: '#60a5fa',
            animation: 'tv-spin 0.8s linear infinite',
          }} />
          <style>{`@keyframes tv-spin { to { transform: rotate(360deg) } }`}</style>
        </div>
      )}
      {state === 'error' && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#94a3b8', fontSize: '0.9rem',
        }}>
          차트를 불러올 수 없습니다
        </div>
      )}
      <div
        id={CONTAINER_ID}
        ref={containerRef}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}
