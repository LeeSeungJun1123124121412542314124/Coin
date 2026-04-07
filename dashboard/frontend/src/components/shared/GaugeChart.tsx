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

  // 반원 arc
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const arcX = (deg: number) => cx + r * Math.cos(toRad(deg - 90))
  const arcY = (deg: number) => cy + r * Math.sin(toRad(deg - 90))

  const arcPath = `M ${arcX(-90)} ${arcY(-90)} A ${r} ${r} 0 0 1 ${arcX(90)} ${arcY(90)}`

  const color =
    value <= 25 ? '#ef4444'
    : value <= 50 ? '#f97316'
    : value <= 75 ? '#22c55e'
    : '#a855f7'

  // 바늘
  const needleRad = toRad(angle)
  const needleLen = r - 6
  const nx = cx + needleLen * Math.cos(needleRad)
  const ny = cy + needleLen * Math.sin(needleRad)

  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={size} height={size / 2 + 20} style={{ overflow: 'visible' }}>
        {/* 배경 반원 */}
        <path d={arcPath} fill="none" stroke="#334155" strokeWidth={12} strokeLinecap="round" />
        {/* 색상 반원 */}
        <path
          d={arcPath}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${pct * Math.PI * r} ${Math.PI * r}`}
        />
        {/* 바늘 */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#e2e8f0" strokeWidth={2} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={4} fill="#e2e8f0" />
        {/* 값 */}
        <text x={cx} y={cy + 24} textAnchor="middle" fill={color} fontSize={18} fontWeight="bold">
          {value}
        </text>
      </svg>
      <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginTop: 2 }}>{label}</div>
    </div>
  )
}
