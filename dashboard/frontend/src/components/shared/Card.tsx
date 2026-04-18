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
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: 12,
        padding: 16,
        ...style,
      }}
      className={className}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
