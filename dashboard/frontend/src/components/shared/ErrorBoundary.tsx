import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

// 렌더 크래시(널 필드 .toFixed() 등)가 앱 전체를 백지로 만드는 것 방지 —
// 해당 서브트리만 에러 카드로 대체하고 새로고침 경로 제공.
interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: unknown): State {
    return { hasError: true, message: error instanceof Error ? error.message : String(error) }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('렌더 오류:', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        minHeight: '60vh', gap: 16, padding: 24, textAlign: 'center',
      }}>
        <div style={{ fontSize: '2rem', fontWeight: 700 }}>!</div>
        <div style={{ color: 'var(--text)', fontSize: '1rem' }}>화면을 표시하는 중 오류가 발생했습니다.</div>
        <div style={{ color: 'var(--text-3)', fontSize: '0.8rem', maxWidth: 480, wordBreak: 'break-word' }}>
          {this.state.message}
        </div>
        <button
          onClick={() => window.location.reload()}
          style={{
            padding: '8px 20px', borderRadius: 8, border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer', fontSize: '0.85rem',
          }}
        >
          새로고침
        </button>
      </div>
    )
  }
}
