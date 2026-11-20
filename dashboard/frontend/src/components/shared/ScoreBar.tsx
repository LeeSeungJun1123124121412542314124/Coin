import { LEVEL_COLORS } from '../../lib/theme'

interface ScoreBarProps {
  score: number
  /** 바 위 레이블 (없으면 "위험도") */
  label?: string
  /** 직접 색상 지정 (없으면 level로 결정) */
  color?: string
  /** 레벨 키 (color가 없을 때 색상 결정에 사용) */
  level?: string
  /** 바 높이(px). 기본 4 */
  height?: number
  /** 점수 표시 형식. 기본 "score/100" */
  scoreFormat?: 'fraction' | 'plain'
}

/**
 * 가로 점수 바 컴포넌트
 * - Research.tsx 용례: <ScoreBar score={cat.score} level={cat.level} />
 * - SPF.tsx 용례:      <ScoreBar label="강세 점수" score={s} color="var(--up)" height={8} scoreFormat="plain" />
 */
export function ScoreBar({
  score,
  label = '위험도',
  color,
  level,
  height = 4,
  scoreFormat = 'fraction',
}: ScoreBarProps) {
  const resolvedColor = color ?? (level ? (LEVEL_COLORS[level] ?? 'var(--accent)') : 'var(--accent)')
  const scoreLabel = scoreFormat === 'plain' ? String(score) : `${score}/100`
  const labelColor = scoreFormat === 'plain' ? 'var(--text-2)' : 'var(--text-3)'
  const valueFontSize = scoreFormat === 'plain' ? '1.1rem' : '0.75rem'
  const valueFontWeight = scoreFormat === 'plain' ? 700 : 600
  const trackColor = 'var(--seg-active)'
  const borderRadius = 999

  return (
    <div style={{ marginBottom: scoreFormat === 'plain' ? 10 : 0, marginTop: scoreFormat === 'plain' ? 0 : 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: scoreFormat === 'plain' ? '0.8rem' : 12, color: labelColor }}>{label}</span>
        <span style={{ fontSize: valueFontSize, color: resolvedColor, fontWeight: valueFontWeight, fontFamily: 'var(--font-mono)' }}>{scoreLabel}</span>
      </div>
      <div style={{ height, background: trackColor, borderRadius, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${score}%`,
          background: resolvedColor,
          borderRadius,
          transition: `width ${scoreFormat === 'plain' ? '0.5s' : '0.4s ease'}`,
        }} />
      </div>
    </div>
  )
}
