import { useEffect, useState } from 'react'
import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom'
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
import { BotReports } from './components/screens/BotReports'
import { Leaderboard } from './components/screens/Leaderboard'
import { Learning } from './components/screens/Learning'
import type { LastUpdatedDetail } from './components/shared/LastUpdated'
import { TickerStrip } from './components/shared/TickerStrip'
import { BASE } from './lib/api'
import { NAV_GROUPS } from './lib/navGroups.ts'

const TABS = [
  { path: '/', label: '대시보드', description: '시장 핵심 카드와 뉴스, 코인·주식 요약을 한 화면에서 봅니다.' },
  { path: '/volume', label: '볼륨트래커', description: '국내 거래대금과 RSI, 공포탐욕 흐름으로 시장 열기를 추적합니다.' },
  { path: '/spf', label: 'SPF', description: '선물 포지션 흐름과 중기 방향 전망을 검증합니다.' },
  { path: '/research', label: '리서치', description: '수집된 데이터를 카테고리별 자동 분석으로 정리합니다.' },
  { path: '/market', label: '시장분석', description: 'VIX, BTC, 핵심 지표와 시장 인사이트를 비교합니다.' },
  { path: '/liquidity', label: '유동성', description: 'TGA, M2, SOMA와 국채 경매로 매크로 유동성을 봅니다.' },
  { path: '/cvd', label: 'CVD 스크리너', description: 'CVD와 가격 다이버전스 기반 알트코인 스크리닝을 확인합니다.' },
  { path: '/whale', label: '고래추적', description: 'Hyperliquid 상위 지갑 포지션과 BTC 방향 합의를 추적합니다.' },
  { path: '/leaderboard', label: '리더보드', description: '지표별 포워드 자동매매 성과와 에쿼티 곡선을 비교합니다.' },
  { path: '/alerts', label: '알림히스토리', description: '전송된 경보와 방향 판정 기록을 심볼별로 확인합니다.' },
  { path: '/bot-reports', label: '봇 리포트', description: '봇이 보낸 일봉 점검, 청산 히트맵, 고래 소식을 종류별로 모아 봅니다.' },
  { path: '/learning', label: '학습', description: '차트로 국면을 판단하고 근거와 함께 모의매매한 뒤 복기합니다.' },
] as const

function Brand() {
  return (
    <Link to="/" className="shell-brand">
      <span className="shell-brand-mark">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 17l5-5 4 4 8-9" />
        </svg>
      </span>
      <span className="shell-brand-name">투자분석기</span>
    </Link>
  )
}

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
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--bg)' }}>
      <h1 style={{ color: 'var(--text)', fontSize: '1.5rem', marginBottom: '2rem' }}>투자분석기</h1>
      <div style={{ display: 'flex', gap: '12px', marginBottom: '2rem', animation: shake ? 'shake 0.5s' : 'none' }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{
            width: 16, height: 16, borderRadius: '50%',
            background: i < pin.length ? 'var(--accent)' : 'transparent',
            border: `2px solid ${i < pin.length ? 'var(--accent)' : 'var(--text-3)'}`,
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
              background: k ? 'var(--surface)' : 'transparent',
              border: '1px solid var(--border)', color: 'var(--text)', fontSize: '1.25rem',
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
  const [pageLastUpdated, setPageLastUpdated] = useState<LastUpdatedDetail>({ time: '', failed: false })
  const activeTab = TABS.find(tab => (
    tab.path === '/' ? location.pathname === '/' : location.pathname.startsWith(tab.path)
  )) ?? TABS[0]
  const activeGroup = NAV_GROUPS.find(group => group.paths.includes(activeTab.path)) ?? NAV_GROUPS[0]

  useEffect(() => {
    setPageLastUpdated({ time: '', failed: false })
  }, [location.pathname])

  useEffect(() => {
    const handleLastUpdated = (event: Event) => {
      const detail = (event as CustomEvent<LastUpdatedDetail>).detail
      setPageLastUpdated(detail)
    }
    window.addEventListener('dashboard:last-updated', handleLastUpdated)
    return () => window.removeEventListener('dashboard:last-updated', handleLastUpdated)
  }, [])

  if (!authenticated) {
    return <PinScreen onSuccess={() => setAuthenticated(true)} />
  }

  const tabByPath = (path: string) => TABS.find(t => t.path === path)

  return (
    <div className="app-shell">
      <TickerStrip>
        {/* 데이터가 있는 상태에서 갱신이 실패하면 오래된 값임을 알린다 */}
        {pageLastUpdated.failed && pageLastUpdated.time ? (
          <span className="shell-updated is-failed">갱신 실패 · 마지막 성공 {pageLastUpdated.time}</span>
        ) : (
          <span className="shell-updated">최종 갱신 {pageLastUpdated.time || '-'}</span>
        )}
      </TickerStrip>

      <header className="shell-masthead">
        <div className="shell-masthead-inner">
          <Brand />
          {/* 묶음 5개 — 누르면 묶음의 첫 화면으로 간다 */}
          <nav className="shell-nav" aria-label="주요 화면">
            {NAV_GROUPS.map(group => (
              <Link
                key={group.label}
                to={group.paths[0]}
                aria-current={group === activeGroup ? 'page' : undefined}
                className={`shell-link${group === activeGroup ? ' shell-link-active' : ''}`}
              >
                {group.label}
                {group.paths.length > 1 && <span className="shell-link-count">{group.paths.length}</span>}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      {/* 묶음 안에 화면이 둘 이상이면 그 화면들의 탭 */}
      {activeGroup.paths.length > 1 && (
        <nav className="shell-subnav" aria-label={`${activeGroup.label} 안의 화면`}>
          <div className="shell-subnav-inner">
            {activeGroup.paths.map(path => (
              <Link
                key={path}
                to={path}
                aria-current={path === activeTab.path ? 'page' : undefined}
                className={`shell-sublink${path === activeTab.path ? ' shell-sublink-active' : ''}`}
              >
                {tabByPath(path)?.label}
              </Link>
            ))}
          </div>
        </nav>
      )}

      <main className="app-main">
        {/* 홈은 판단 제목이 화면 제목 자리를 대신한다 */}
        {activeTab.path !== '/' && (
          <header className="shell-page-head">
            <h1 className="shell-title">{activeTab.label}</h1>
            <p className="shell-desc">{activeTab.description}</p>
          </header>
        )}
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
          <Route path="/bot-reports" element={<BotReports />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/learning" element={<Learning />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      {/* 모바일 아래 탭 — 묶음 5개, 글자만 */}
      <nav className="shell-bottom" aria-label="모바일 메뉴">
        {NAV_GROUPS.map(group => (
          <Link
            key={group.label}
            to={group.paths[0]}
            aria-current={group === activeGroup ? 'page' : undefined}
            className={`shell-bottom-item${group === activeGroup ? ' shell-bottom-active' : ''}`}
          >
            {group.short}
          </Link>
        ))}
      </nav>
    </div>
  )
}
