import type { ReactNode } from 'react'
import { useApi } from '../../hooks/useApi'
import { fmtFixed } from '../../lib/format'
import { changeArrow } from '../../lib/theme'

interface TickerData {
  coins: Array<{ symbol: string; change_24h: number | null }> | null
}

// 맨 위 먹색 시세 띠 — 코인 슬롯의 24시간 등락. 오른쪽 자리(children)에는 앱이 최종 갱신 시각을 넣는다
export function TickerStrip({ children }: { children: ReactNode }) {
  const { data } = useApi<TickerData>('/api/dashboard', 60_000)

  return (
    <div className="shell-ticker">
      <div className="shell-ticker-inner">
        <div className="shell-ticker-coins" aria-label="코인 24시간 등락">
          <span className="shell-ticker-label">24시간</span>
          {(data?.coins ?? []).map(coin => (
            <span key={coin.symbol} className="shell-ticker-coin">
              <b>{coin.symbol}</b>
              <span data-dir={coin.change_24h == null || coin.change_24h === 0 ? 'flat' : coin.change_24h > 0 ? 'up' : 'down'}>
                {coin.change_24h == null ? '—' : `${changeArrow(coin.change_24h)} ${fmtFixed(Math.abs(coin.change_24h), 1)}%`}
              </span>
            </span>
          ))}
        </div>
        {children}
      </div>
    </div>
  )
}
