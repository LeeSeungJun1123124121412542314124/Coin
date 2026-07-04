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
import { Simulator } from './components/screens/Simulator'
import { Leaderboard } from './components/screens/Leaderboard'
import { BASE } from './lib/api'

// 탭 정의
const TABS = [
  { path: '/', label: '대시보드' },
  { path: '/volume', label: '볼륨 트래커' },
  { path: '/spf', label: 'SPF' },
  { path: '/research', label: '리서치' },
  { path: '/market', label: '시장 분석' },
  { path: '/liquidity', label: '유동성' },
  { path: '/cvd', label: 'CVD 스크리너' },
  { path: '/whale', label: '고래 추적' },
  { path: '/alerts', label: '알림 히스토리' },
  { path: '/simulator', label: '시뮬레이터' },
  { path: '/leaderboard', label: '리더보드' },
] as const

const PRIMARY_TABS = [
  { path: '/', label: '홈' },
  { path: '/spf', label: 'SPF' },
  { path: '/simulator', label: '검증' },
  { path: '/leaderboard', label: '순위' },
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
      <aside className="app-desktop-sidebar">
        <div className="app-desktop-brand">
          <div className="app-brand-title">투자분석기</div>
          <div className="app-brand-subtitle">시장 전망 · 예측 검증</div>
        </div>
        <nav className="app-sidebar-nav" aria-label="PC 주요 화면">
          {TABS.map(tab => (
            <NavLink
              key={tab.path}
              to={tab.path}
              end={tab.path === '/'}
              className={({ isActive }) => `app-sidebar-link${isActive ? ' app-sidebar-link-active' : ''}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <header className="app-topbar">
        <div className="app-brand-row">
          <div>
            <div className="app-brand-title">투자분석기</div>
            <div className="app-brand-subtitle">시장 전망 · 예측 검증 · 포트폴리오 실험</div>
          </div>
          <div className="app-status-pill">실시간 대시보드</div>
        </div>
        <nav className="app-tab-scroll" aria-label="주요 화면">
        {TABS.map(tab => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end={tab.path === '/'}
            className={({ isActive }) => `app-tab-link${isActive ? ' app-tab-link-active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
        </nav>
      </header>

      {/* 탭 콘텐츠 */}
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
          <Route path="/simulator" element={<Simulator />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <nav className="app-bottom-nav" aria-label="모바일 핵심 화면">
        {PRIMARY_TABS.map(tab => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end={tab.path === '/'}
            className={({ isActive }) => `app-bottom-link${isActive ? ' app-bottom-link-active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
