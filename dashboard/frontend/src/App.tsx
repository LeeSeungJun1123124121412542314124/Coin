import { useEffect, useRef, useState } from 'react'
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
import { BotReports } from './components/screens/BotReports'
import { Leaderboard } from './components/screens/Leaderboard'
import { Learning } from './components/screens/Learning'
import type { LastUpdatedDetail } from './components/shared/LastUpdated'
import { BASE } from './lib/api'
import { NAV_GROUPS, MOBILE_PRIMARY, groupOf } from './lib/navGroups.ts'

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

// 경로별 아이콘 path (24 viewBox 선 아이콘)
const ICONS: Record<string, string> = {
  '/': 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
  '/market': 'M3 3v18h18M7 15l4-4 3 3 5-6',
  '/liquidity': 'M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z',
  '/volume': 'M5 20V10M10 20V4M15 20v-7M20 20V8',
  '/spf': 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5',
  '/cvd': 'M4 5h16l-6 7v6l-4 2v-8z',
  '/whale': 'M4 12a8 8 0 1 0 16 0a8 8 0 1 0-16 0M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
  '/research': 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6',
  '/leaderboard': 'M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4',
  '/alerts': 'M6 16v-5a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0',
  '/bot-reports': 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5',
  '/learning': 'M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
}

function Icon({ name }: { name: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  )
}

function Brand() {
  return (
    <div className="shell-brand">
      <span className="shell-brand-mark">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--bg)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 17l5-5 4 4 8-9" />
        </svg>
      </span>
      <span>
        <span className="shell-brand-name">투자분석기</span>
        <span className="shell-brand-sub">시장 · 파생 · 학습</span>
      </span>
    </div>
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
  const [moreOpen, setMoreOpen] = useState(false)
  const moreBtnRef = useRef<HTMLButtonElement>(null)
  const sheetRef = useRef<HTMLDivElement>(null)
  const activeTab = TABS.find(tab => (
    tab.path === '/' ? location.pathname === '/' : location.pathname.startsWith(tab.path)
  )) ?? TABS[0]
  const primaryPaths = MOBILE_PRIMARY.map(m => m.path)
  const moreActive = !primaryPaths.includes(activeTab.path)

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

  // 더보기 시트: 열릴 때 첫 링크로 포커스, Esc 닫기, Tab은 시트 안에서 순환, 닫히면 버튼으로 복귀
  useEffect(() => {
    if (!moreOpen) return
    const sheet = sheetRef.current
    const btn = moreBtnRef.current
    const links = () => Array.from(sheet?.querySelectorAll<HTMLElement>('a[href]') ?? [])
    links()[0]?.focus()
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMoreOpen(false)
      } else if (e.key === 'Tab') {
        const items = links()
        if (items.length === 0) return
        const first = items[0]
        const last = items[items.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      btn?.focus()
    }
  }, [moreOpen])

  if (!authenticated) {
    return <PinScreen onSuccess={() => setAuthenticated(true)} />
  }

  const tabByPath = (path: string) => TABS.find(t => t.path === path)
  const closeMore = () => setMoreOpen(false)

  return (
    <div className="app-shell">
      <aside className="shell-sidebar">
        <Brand />
        <nav className="shell-nav" aria-label="주요 화면">
          {NAV_GROUPS.map(group => (
            <div key={group.label} className="shell-group">
              <div className="shell-group-label">{group.label}</div>
              {group.paths.map(path => (
                <NavLink
                  key={path}
                  to={path}
                  end={path === '/'}
                  className={({ isActive }) => `shell-link${isActive ? ' shell-link-active' : ''}`}
                >
                  <Icon name={path} />
                  <span>{tabByPath(path)?.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      <main className="app-main">
        <header className="shell-page-head">
          <div className="shell-page-head-text">
            <div className="shell-crumb">{groupOf(activeTab.path)} / {activeTab.label}</div>
            <h1 className="shell-title">{activeTab.label}</h1>
            <p className="shell-desc">{activeTab.description}</p>
          </div>
          {/* 데이터가 있는 상태에서 갱신이 실패하면 오래된 값임을 알린다 */}
          {pageLastUpdated.failed && pageLastUpdated.time ? (
            <span className="shell-updated is-failed">갱신 실패 · 마지막 성공 {pageLastUpdated.time}</span>
          ) : (
            <span className="shell-updated">최종 갱신 {pageLastUpdated.time || '-'}</span>
          )}
        </header>
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
      <nav className="shell-bottom" aria-label="모바일 메뉴">
        {MOBILE_PRIMARY.map(m => (
          <NavLink
            key={m.path}
            to={m.path}
            end={m.path === '/'}
            className={({ isActive }) => `shell-bottom-item${isActive ? ' shell-bottom-active' : ''}`}
          >
            <Icon name={m.path} />
            <span>{m.label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          className={`shell-bottom-item${moreActive ? ' shell-bottom-active' : ''}`}
          ref={moreBtnRef}
          onClick={() => setMoreOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
        >
          <Icon name="more" />
          <span>더보기</span>
        </button>
      </nav>
      {moreOpen && (
        <div className="shell-sheet-backdrop" onClick={closeMore}>
          <div className="shell-sheet" ref={sheetRef} role="dialog" aria-modal="true" aria-label="전체 메뉴" onClick={e => e.stopPropagation()}>
            {NAV_GROUPS.map(group => {
              const rest = group.paths.filter(path => !primaryPaths.includes(path))
              if (rest.length === 0) return null
              return (
                <div key={group.label} className="shell-group">
                  <div className="shell-group-label">{group.label}</div>
                  {rest.map(path => (
                    <NavLink
                      key={path}
                      to={path}
                      end={path === '/'}
                      onClick={closeMore}
                      className={({ isActive }) => `shell-link${isActive ? ' shell-link-active' : ''}`}
                    >
                      <Icon name={path} />
                      <span>{tabByPath(path)?.label}</span>
                    </NavLink>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
