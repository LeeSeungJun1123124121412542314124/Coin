import { useState } from 'react'
import './index.css'
import { Dashboard } from './components/screens/Dashboard'
import { SPF } from './components/screens/SPF'
import { Volume } from './components/screens/Volume'
import { Market } from './components/screens/Market'

// 탭 정의
const TABS = [
  { id: 'dashboard', label: '대시보드' },
  { id: 'volume', label: '볼륨 트래커' },
  { id: 'spf', label: 'SPF' },
  { id: 'research', label: '리서치' },
  { id: 'market', label: '시장 분석' },
  { id: 'liquidity', label: '유동성' },
  { id: 'cvd', label: 'CVD 스크리너' },
  { id: 'whale', label: '고래 추적' },
] as const

type TabId = typeof TABS[number]['id']

// PIN 인증 화면
function PinScreen({ onSuccess }: { onSuccess: () => void }) {
  const [pin, setPin] = useState('')
  const [shake, setShake] = useState(false)
  const CORRECT_PIN = import.meta.env.VITE_PIN_CODE ?? '0000'

  const handleKey = (digit: string) => {
    if (pin.length >= 4) return
    const next = pin + digit
    setPin(next)
    if (next.length === 4) {
      if (next === CORRECT_PIN) {
        onSuccess()
      } else {
        setShake(true)
        setTimeout(() => { setPin(''); setShake(false) }, 500)
      }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#0f1117' }}>
      <h1 style={{ color: '#fff', fontSize: '1.5rem', marginBottom: '2rem' }}>크립토 인사이트</h1>
      {/* PIN 도트 */}
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
      {/* 키패드 */}
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

// 탭별 화면 플레이스홀더 (Phase 1~4에서 순차 구현)
function PlaceholderScreen({ title }: { title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '16rem', color: '#64748b' }}>
      <p>{title} — 준비 중</p>
    </div>
  )
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>('dashboard')

  if (!authenticated) {
    return <PinScreen onSuccess={() => setAuthenticated(true)} />
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0f1117', color: '#e2e8f0' }}>
      {/* 상단 내비게이션 */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 10,
        background: 'rgba(15,17,23,0.9)', backdropFilter: 'blur(8px)',
        borderBottom: '1px solid #1e293b', padding: '8px 16px',
        display: 'flex', gap: '4px', overflowX: 'auto',
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '8px 16px', borderRadius: 8, border: 'none',
              fontSize: '0.875rem', fontWeight: 500, whiteSpace: 'nowrap', cursor: 'pointer',
              background: activeTab === tab.id ? '#2563eb' : 'transparent',
              color: activeTab === tab.id ? '#fff' : '#94a3b8',
              transition: 'all 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* 탭 콘텐츠 */}
      <main style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px 16px' }}>
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'volume' && <Volume />}
        {activeTab === 'spf' && <SPF />}
        {activeTab === 'research' && <PlaceholderScreen title="리서치" />}
        {activeTab === 'market' && <Market />}
        {activeTab === 'liquidity' && <PlaceholderScreen title="유동성" />}
        {activeTab === 'cvd' && <PlaceholderScreen title="CVD 스크리너" />}
        {activeTab === 'whale' && <PlaceholderScreen title="고래 추적" />}
      </main>
    </div>
  )
}
