import { C } from '../../lib/theme'

interface GaugeChartProps {
  value: number  // 0~100
  label: string
  size?: number
}

export function GaugeChart({ value, label, size = 120 }: GaugeChartProps) {
  const pct = Math.min(100, Math.max(0, value)) / 100
  const angle = pct * 180 - 90  // -90 ~ 90deg
  const r = size / 2 - 10
  const cx = size / 2
  const cy = size / 2

  const toRad = (deg: number) => (deg * Math.PI) / 180
  const arcX = (deg: number) => cx + r * Math.cos(toRad(deg - 90))
  const arcY = (deg: number) => cy + r * Math.sin(toRad(deg - 90))

  const arcPath = `M ${arcX(-90)} ${arcY(-90)} A ${r} ${r} 0 0 1 ${arcX(90)} ${arcY(90)}`

  const color =
    value <= 25 ? C.danger
    : value <= 50 ? C.warn
    : value <= 75 ? C.ok
    : C.violet

  const needleRad = toRad(angle)
  const needleLen = r - 6
  const nx = cx + needleLen * Math.cos(needleRad)
  const ny = cy + needleLen * Math.sin(needleRad)

  return (
    <div style={{ textAlign: 'center' }}>
      {/* 게이지 arc + 바늘만 SVG로 */}
      <svg width={size} height={size / 2 + 8} style={{ display: 'block', margin: '0 auto' }}>
        <path d={arcPath} fill="none" stroke={C.segActive} strokeWidth={12} strokeLinecap="round" />
        <path
          d={arcPath}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${pct * Math.PI * r} ${Math.PI * r}`}
        />
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={C.text} strokeWidth={2} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={4} fill={C.text} />
      </svg>

      {/* 수치 + 레이블 — SVG 아래 별도 블록 */}
      <div style={{ marginTop: 6 }}>
        <span style={{ fontSize: '1.6rem', fontWeight: 700, color, fontFamily: 'var(--font-mono)' }}>{value}</span>
      </div>
      <div style={{ color: 'var(--text-2)', fontSize: '0.8rem', marginTop: 2 }}>{label}</div>
    </div>
  )
}
