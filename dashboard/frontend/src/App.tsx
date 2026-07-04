import { useState } from 'react'
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import './index.css'
import { Dashboard } from './components/screens/Dashboard'
import { SPF } from './components/screens/SPF'
import { Volume } from './components/screens/Volume'
import { Market } from './components/screens/Market'
import { Liquidity } from './components/screens/Liquidity'
import { Alt } from './components/screens/Alt'
import { Whale } from './components/screens/Whale'
import { Research } from './components/screens/Research'
import { Alerts } from './components/screens/Alerts'
import { Leaderboard } from './components/screens/Leaderboard'
import { BASE } from './lib/api'

const TABS = [
  { path: '/', label: '대시보드', description: '시장 핵심 카드와 뉴스, 코인·주식 요약을 한 화면에서 봅니다.' },
  { path: '/volume', label: '볼륨트래커', description: '국내 거래대금과 RSI, 공포탐욕 흐름으로 시장 열기를 추적합니다.' },
  { path: '/spf', label: 'SPF', description: '선물 포지션 흐름과 중기 방향 전망을 검증합니다.' },
  { path: '/research', label: '리서치', description: '수집된 데이터를 카테고리별 자동 분석으로 정리합니다.' },
  { path: '/market', label: '시장분석', description: 'VIX, BTC, 핵심 지표와 시장 인사이트를 비교합니다.' },
  { path: '/liquidity', label: '유동성', description: 'TGA, M2, SOMA와 국채 경매로 매크로 유동성을 봅니다.' },
  { path: '/cvd', label: 'CVD 스크리너', description: 'CVD와 가격 다이버전스 기반 알트코인 스크리닝을 확인합니다.' },
  { path: '/whale', label: '고래추적', description: 'Hyperliquid 상위 지갑 포지션과 BTC 방향 합의를 추적합니다.' },
  { path: '/alerts', label: '알림히스토리', description: '전송된 경보와 방향 판정 기록을 심볼별로 확인합니다.' },
  { path: '/leaderboard', label: '리더보드', description: '지표별 포워드 자동매매 성과와 에쿼티 곡선을 비교합니다.' },
] as const

function PinScreen({ onSuccess }: { onSuccess: () => void }) {
  const [pin, setPin] = useState('')
  const [shake, setShake] = useState(false)

  const handleKey = async (digit: string) => {
    if (pin.length >= 4) return
    const next = pin + digit
    setPin(next)
    if (next.length === 4) {
      try {
        const res = await fetch(`${BASE}/api/auth/verify-pin`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: next }),
        })
        if (res.ok) {
          const data = await res.json()
          sessionStorage.setItem('auth_token', data.token)
          onSuccess()
        } else {
          setShake(true)
          setTimeout(() => { setPin(''); setShake(false) }, 500)
        }
      } catch {
        setShake(true)
        setTimeout(() => { setPin(''); setShake(false) }, 500)
      }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#0f1117' }}>
      <h1 style={{ color: '#fff', fontSize: '1.5rem', marginBottom: '2rem' }}>투자분석기</h1>
      <div style={{ display: 'flex', gap: '12px', marginBottom: '2rem', animation: shake ? 'shake 0.5s' : 'none' }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{
            width: 16, height: 16, borderRadius: '50%',
            background: i < pin.length ? '#60a5fa' : 'transparent',
            border: `2px solid ${i < pin.length ? '#60a5fa' : '#64748b'}`,
            transition: 'all 0.1s',
          }} />
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
        {['1','2','3','4','5','6','7','8','9','','0','⌫'].map((k, i) => (
          <button
            key={i}
            onClick={() => {
              if (k === '⌫') setPin(p => p.slice(0, -1))
              else if (k) handleKey(k)
            }}
            disabled={!k}
            style={{
              width: 64, height: 64, borderRadius: 12,
              background: k ? '#1e293b' : 'transparent',
              border: 'none', color: '#fff', fontSize: '1.25rem',
              cursor: k ? 'pointer' : 'default', opacity: k ? 1 : 0,
            }}
          >
            {k}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const [authenticated, setAuthenticated] = useState(() => {
    return !!sessionStorage.getItem('auth_token')
  })
  const activeTab = TABS.find(tab => (
    tab.path === '/' ? location.pathname === '/' : location.pathname.startsWith(tab.path)
  )) ?? TABS[0]

  if (!authenticated) {
    return <PinScreen onSuccess={() => setAuthenticated(true)} />
  }

  return (
    <div className="app-shell">
      <header className="mock-top-ticker">
        <div className="mock-brand">
          <span className="mock-brand-name">투자분석기</span>
          <span className="mock-brand-separator">|</span>
          <span className="mock-brand-section">{activeTab.label}</span>
        </div>
        <div className="mock-header-title">
          <span>{activeTab.description}</span>
          <span className="mock-header-meta">마지막 업데이트 : 화면별 데이터 기준</span>
        </div>
      </header>
      <aside className="mock-sidebar">
        <nav className="mock-sidebar-nav" aria-label="주요 화면">
          {TABS.map(tab => (
            <NavLink
              key={tab.path}
              to={tab.path}
              end={tab.path === '/'}
              className={({ isActive }) => `mock-sidebar-link${isActive ? ' mock-sidebar-link-active' : ''}`}
            >
              <b>{tab.label}</b>
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/volume" element={<Volume />} />
          <Route path="/spf" element={<SPF />} />
          <Route path="/research" element={<Research />} />
          <Route path="/market" element={<Market />} />
          <Route path="/liquidity" element={<Liquidity />} />
          <Route path="/cvd" element={<Alt />} />
          <Route path="/whale" element={<Whale />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <nav className="mock-bottom-nav" aria-label="모바일 전체 메뉴">
        {TABS.map(tab => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end={tab.path === '/'}
            className={({ isActive }) => `mock-bottom-link${isActive ? ' mock-bottom-link-active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
