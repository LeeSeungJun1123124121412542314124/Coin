// 스켈레톤 로딩 공통 컴포넌트 — shimmer 애니메이션 적용
// @keyframes shimmer는 index.css에 정의됨
import type { CSSProperties } from 'react'

const shimmer: CSSProperties = {
  background: 'linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%)',
  backgroundSize: '200% 100%',
  animation: 'shimmer 1.5s infinite',
  borderRadius: 6,
}

/** 한 줄 스켈레톤 */
export function SkeletonLine({ width = '100%', height = 16 }: { width?: string | number; height?: number }) {
  return <div style={{ ...shimmer, width, height, marginBottom: 8 }} />
}

/** 카드 형태 스켈레톤 */
export function SkeletonCard({ height = 120 }: { height?: number }) {
  return (
    <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16, height }}>
      <SkeletonLine width="60%" height={14} />
      <SkeletonLine width="40%" height={24} />
      <SkeletonLine width="80%" height={12} />
    </div>
  )
}

/** 차트 영역 스켈레톤 */
export function SkeletonChart({ height = 200 }: { height?: number }) {
  return <div style={{ ...shimmer, width: '100%', height }} />
}

/** 기본 스켈레톤 레이아웃 — 4개 카드 + 차트 */
export default function Skeleton() {
  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        {[1, 2, 3, 4].map(i => <SkeletonCard key={i} />)}
      </div>
      <SkeletonChart />
    </div>
  )
}
