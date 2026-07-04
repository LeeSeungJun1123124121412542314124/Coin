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

const TICKERS = [
  { label: 'BTC/USDT', value: '103,512.6', change: '0.68%', up: true },
  { label: 'ETH/USDT', value: '2,489.21', change: '0.35%', up: false },
  { label: 'SOL/USDT', value: '171.32', change: '1.20%', up: true },
  { label: 'XRP/USDT', value: '2.35', change: '0.42%', up: false },
  { label: 'TOTAL', value: '2.48T', change: '0.36%', up: true },
  { label: 'BTC.D', value: '52.61%', change: '0.15%', up: false },
  { label: 'USDT.KRW', value: '1,368.5', change: '0.09%', up: true },
] as const

// 탭 정의
const TABS = [
  { path: '/', label: '대시보드', icon: '▦' },
  { path: '/market', label: '시장 분석', icon: '⌁' },
  { path: '/spf', label: '예측 모델', icon: '◎' },
  { path: '/volume', label: '알트코인 분석', icon: '✣' },
  { path: '/liquidity', label: '온체인 분석', icon: '⌘' },
  { path: '/leaderboard', label: '포트폴리오', icon: '▣' },
  { path: '/alerts', label: '알림', icon: '♢' },
  { path: '/research', label: '리포트', icon: '▤' },
  { path: '/cvd', label: '설정', icon: '⚙' },
] as const

const PRIMARY_TABS = [
  { path: '/', label: '대시보드', icon: '▦' },
  { path: '/market', label: '시장', icon: '⌁' },
  { path: '/leaderboard', label: '포트폴리오', icon: '▣' },
  { path: '/alerts', label: '알림', icon: '♢' },
] as const

// PIN 인증 화면 — 서버 측 검증 후 토큰 발급
function PinScreen({ onSuccess }: { onSuccess: () => void }) {
  const [pin, setPin] = useState('')
  const [shake, setShake] = useState(false)

  const handleKey = async (digit: string) => {
    if (pin.length >= 4) return
    const next = pin + digit
    setPin(next)
    if (next.length === 4) {
      try {
        // apiFetch와 동일한 BASE 사용 — 프론트·API 오리진이 다른 배포에서도 로그인 동작
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
      <h1 style={{ color: '#fff', fontSize: '1.5rem', marginBottom: '2rem' }}>크립토 인사이트</h1>
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
        <div className="mock-ticker-strip">
          {TICKERS.map(item => (
            <div className="mock-ticker-item" key={item.label}>
              <span>{item.label}</span>
              <b>{item.value}</b>
              <em className={item.up ? 'mock-up' : 'mock-down'}>{item.up ? '▲' : '▼'} {item.change}</em>
            </div>
          ))}
        </div>
        <div className="mock-top-actions">
          <span>☼</span>
          <span>☾</span>
          <span className="mock-bell">♧<b>3</b></span>
          <span>◎</span>
          <span>기본 계정⌄</span>
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
