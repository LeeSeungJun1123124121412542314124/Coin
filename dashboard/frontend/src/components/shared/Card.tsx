import type { CSSProperties } from 'react'

interface CardProps {
  children: React.ReactNode
  className?: string
  onClick?: () => void
  style?: CSSProperties
}

export function Card({ children, className = '', onClick, style }: CardProps) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-card)',
        padding: '18px 20px',
        ...style,
      }}
      className={className}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
