import { useState } from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
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
  { path: '/', label: '대시보드', icon: '▦' },
  { path: '/market', label: '시장 분석', icon: '⌁' },
  { path: '/spf', label: 'SPF', icon: '◎' },
  { path: '/research', label: '뉴스', icon: '▤' },
  { path: '/volume', label: '코인 가격', icon: '✣' },
  { path: '/leaderboard', label: '한국 주식', icon: '▣' },
  { path: '/liquidity', label: '알트코인 시즌', icon: '⌘' },
  { path: '/cvd', label: '시장 지표', icon: '⚙' },
] as const

const PRIMARY_TABS = [
  { path: '/', label: '대시보드', icon: '▦' },
  { path: '/market', label: '시장', icon: '⌁' },
  { path: '/leaderboard', label: '주식', icon: '▣' },
  { path: '/alerts', label: '알림', icon: '♢' },
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
  const [authenticated, setAuthenticated] = useState(() => {
    return !!sessionStorage.getItem('auth_token')
  })

  if (!authenticated) {
    return <PinScreen onSuccess={() => setAuthenticated(true)} />
  }

  return (
    <div className="app-shell">
      <header className="mock-top-ticker">
        <div className="mock-brand">
          <span className="mock-brand-mark">◉</span>
          <span className="mock-brand-name">투자분석기</span>
        </div>
        <div className="mock-header-title">실시간 시장 데이터 대시보드</div>
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
              <span>{tab.icon}</span>
              <b>{tab.label}</b>
            </NavLink>
          ))}
        </nav>
        <div className="mock-api-status">
          <div><span>API 연동</span><b><i />연결됨</b></div>
          <div><span>데이터 갱신</span><button type="button">⟳</button></div>
          <small>1분 전</small>
        </div>
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
      <nav className="mock-bottom-nav" aria-label="모바일 핵심 화면">
        {PRIMARY_TABS.map(tab => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end={tab.path === '/'}
            className={({ isActive }) => `mock-bottom-link${isActive ? ' mock-bottom-link-active' : ''}`}
          >
            <span>{tab.icon}</span>
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
