import type { CSSProperties } from 'react'
import { useApi } from '../../hooks/useApi'
import { useIsMobile } from '../../hooks/useIsMobile'
import { Card } from '../shared/Card'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import ErrorState from '../shared/ErrorState'
import Skeleton from '../shared/Skeleton'
import LastUpdated from '../shared/LastUpdated'
import { C, changeColor, changeArrow, softBg } from '../../lib/theme'
import { fmtFixed, fmtSignedPct } from '../../lib/format'
import { parseReason } from './spfReasons'

interface SpfCurrent {
  date: string
  oi: number | null        // Bybit 선형 OI = BTC 개수 (USD 환산 = oi × price)
  price: number | null     // BTC 가격 (USD 환산용)
  fr: number | null
  oi_change_3d: number
  oi_change_7d: number
  cum_fr_3d: number
  cum_fr_7d: number
  flow: string
  bearish_score: number
  bullish_score: number
  oi_consecutive_up: number
  oi_surge_alert: string | null
}

interface SimilarPattern {
  date: string
  similarity: number
  flow: string
  change_3d_pct: number
  bearish_score: number
}

interface TodayPrediction {
  direction: string
  confidence: number
  up_prob: number
  down_prob: number
  reasons: string  // JSON string
}

interface HorizonStat {
  expected: number          // 백테스트 기대 적중률(%)
  realized: number | null   // 운영 실측 적중률(%) — 표본 없으면 null
  n: number                 // 판정된 방향 커밋 예측 수
}

type HorizonResult = 'hit' | 'miss' | 'neutral'
type HorizonResultKey = keyof typeof HORIZON_RESULT_META

interface SpfData {
  current: SpfCurrent | null
  history: SpfCurrent[]
  similar_patterns: SimilarPattern[]
  today_prediction: TodayPrediction | null
}

interface PredHistory {
  predictions: Array<{
    date: string
    direction: string
    confidence: number
    result: string | null
    result_7d: HorizonResult | null
    result_14d: HorizonResult | null
    result_30d: HorizonResult | null
    result_60d: HorizonResult | null
    up_prob: number
    down_prob: number
  }>
  stats: Record<string, HorizonStat>  // "7" | "14" | "30" | "60"
}

const FLOW_LABELS: Record<string, string> = {
  long_entry: '롱 신규 진입',
  short_entry: '숏 신규 진입',
  long_exit: '롱 청산',
  short_exit: '숏 청산',
  neutral: '중립',
}

const HISTORY_HORIZONS = [
  { label: '7일', field: 'result_7d' },
  { label: '14일', field: 'result_14d' },
  { label: '30일', field: 'result_30d' },
  { label: '60일', field: 'result_60d' },
] as const

const HORIZON_RESULT_META = {
  'hit': { symbol: '✓', color: C.ok, text: '적중' },
  'miss': { symbol: '✗', color: C.warn, text: '빗나감' },
  'neutral': { symbol: '–', color: C.text2, text: '중립' },
  pending: { symbol: '·', color: C.text3, text: '대기' },
} as const

function getHorizonResultMeta(result: string | null) {
  if (result && result in HORIZON_RESULT_META) {
    return HORIZON_RESULT_META[result as HorizonResultKey]
  }
  return HORIZON_RESULT_META.pending
}


const TONE_COLOR = { up: 'var(--up)', down: 'var(--down)', flat: 'var(--text-2)' } as const
const TONE_TAG = { up: '▲ 상승 쪽', down: '▼ 하락 쪽', flat: '' } as const
const MONO = { fontFamily: 'var(--font-mono)' } as const
const gridCols = (cols: string) => ({ '--spf-cols': cols }) as CSSProperties

function dirTone(direction: string): 'up' | 'down' | 'flat' {
  return direction === '상승' ? 'up' : direction === '하락' ? 'down' : 'flat'
}
function dirArrow(direction: string) {
  return direction === '상승' ? '▲' : direction === '하락' ? '▼' : '–'
}

// 부호 있는 변화율(비율값 → %)을 방향색·▲▼와 함께 표시
function changeCell(ratio: number | null | undefined) {
  if (ratio == null) return { text: '—', color: 'var(--text)' }
  const pct = ratio * 100
  return { text: `${changeArrow(pct)} ${fmtSignedPct(pct)}`, color: changeColor(pct) }
}

export function SPF() {
  const { data, loading, error, refetch, lastUpdated } = useApi<SpfData>('/api/spf-data', 120_000)
  const { data: predData } = useApi<PredHistory>('/api/prediction-history')
  const isMobile = useIsMobile()

  if (error && !data) return <ErrorState error={error} onRetry={refetch} />
  if (loading || !data) return <Skeleton />

  const { current, history, similar_patterns, today_prediction } = data
  let reasons: string[] = []
  try {
    const parsed = today_prediction?.reasons ? JSON.parse(today_prediction.reasons) : []
    reasons = Array.isArray(parsed) ? parsed : []
  } catch {
    reasons = []
  }
  const parsedReasons = reasons.map(parseReason)

  const verdictTone = dirTone(today_prediction?.direction ?? '')
  const verdictText = verdictTone === 'flat' ? '뚜렷한 방향이 없습니다' : `${today_prediction?.direction} 쪽이 우세합니다`

  // 히스토리 차트 데이터 (오래된 순)
  const chartData = [...(history || [])].reverse().slice(-30).map(r => ({
    date: r.date?.slice(5),
    bearish: r.bearish_score,
    bullish: r.bullish_score,
    oi_change: +(r.oi_change_3d * 100).toFixed(2),
  }))

  const bearish = current?.bearish_score ?? 0
  const bullish = current?.bullish_score ?? 0
  const oi3 = changeCell(current?.oi_change_3d)
  const oi7 = changeCell(current?.oi_change_7d)
  const frPct = (v: number | null | undefined) => (v == null ? '—' : `${fmtFixed(v * 100, 4)}%`)
  // 현재 FR 강조: 과열(> 0.03%)은 주의색, 역발상 구간(< −0.01%)은 정상색
  const frColor = (current?.fr ?? 0) > 0.0003 ? 'var(--warn)' : (current?.fr ?? 0) < -0.0001 ? 'var(--ok)' : 'var(--text)'
  const flowLabel = FLOW_LABELS[current?.flow ?? 'neutral'] ?? current?.flow

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <LastUpdated timestamp={lastUpdated} failed={!!error} />
      {/* 역할 라벨 — 시뮬레이터(수익 검증)와 구분 */}
      <div style={{ color: 'var(--text-3)', fontSize: '0.8rem', lineHeight: 1.5 }}>
        <b style={{ color: 'var(--text-2)' }}>시장 방향 전망 · 선물 포지션 흐름</b> — 지금 어디로 향하나(복합 모델)와 시장이 어떤 상태인가(OI/FR 쏠림)를 봅니다.
        <span style={{ color: 'var(--text-3)' }}> 지표별 수익 검증은 시뮬레이터 탭에서.</span>
      </div>
      {/* OI 급등 경고 배너 */}
      {current?.oi_surge_alert && (
        <div style={{
          background: softBg(current.oi_surge_alert === 'CRITICAL' ? C.danger : C.warn, 0.15),
          border: `1px solid ${current.oi_surge_alert === 'CRITICAL' ? 'var(--danger)' : 'var(--warn)'}`,
          borderRadius: 8, padding: '10px 16px',
          color: current.oi_surge_alert === 'CRITICAL' ? 'var(--danger)' : 'var(--warn-text)',
          fontWeight: 600, fontSize: '0.9rem',
        }}>
          OI {current.oi_surge_alert === 'CRITICAL' ? '급등 경고' : '주의'} — 3일 {(current.oi_change_3d * 100).toFixed(1)}% 상승
        </div>
      )}

      {/* 방향 전망(맨 위) + 예측 근거 */}
      <div className="spf-grid" style={gridCols('1fr 1.4fr')}>
        {/* 복합 방향 전망 (7/14/30/60일 채점 — 옛 3일 예측 폐기) */}
        <Card style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
            <h2 className="spf-h">중기 방향 전망</h2>
            {today_prediction && (
              <span className="v2-nowrap" style={{ fontSize: 13, color: 'var(--text-2)' }}>
                신뢰도 <span style={{ ...MONO, fontWeight: 600, color: 'var(--text)' }}>{today_prediction.confidence}%</span>
              </span>
            )}
          </div>
          {today_prediction ? (
            <>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                <span className="v2-nowrap" style={{ fontSize: isMobile ? 34 : 44, fontWeight: 700, letterSpacing: '-0.02em', color: TONE_COLOR[verdictTone] }}>
                  {dirArrow(today_prediction.direction)} {today_prediction.direction}
                </span>
                <span style={{ fontSize: 14, color: 'var(--text-2)' }}>{verdictText}</span>
              </div>
              {/* 상승/하락 확률 막대 */}
              <div aria-hidden="true" style={{ display: 'flex', height: 12, borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ width: `${today_prediction.up_prob}%`, background: 'var(--up)' }} />
                <div style={{ width: `${today_prediction.down_prob}%`, background: 'var(--down)' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                <span className="v2-nowrap" style={{ color: 'var(--up)' }}>▲ 상승 <span style={{ ...MONO, fontWeight: 600 }}>{today_prediction.up_prob}%</span></span>
                <span className="v2-nowrap" style={{ color: 'var(--down)' }}>▼ 하락 <span style={{ ...MONO, fontWeight: 600 }}>{today_prediction.down_prob}%</span></span>
              </div>
            </>
          ) : (
            <div style={{ color: 'var(--text-3)', fontSize: 14 }}>예측 데이터 없음</div>
          )}
        </Card>

        {/* 예측 근거 — 팩터 이름은 쉬운 말로, 문장형 근거는 그대로 */}
        {parsedReasons.length > 0 && (
          <Card style={{ padding: '18px 20px 8px' }}>
            <div className="spf-head">
              <h2 className="spf-h">예측 근거</h2>
              <span className="spf-cap">각 요인이 전망을 어느 쪽으로 미는지와 그 세기입니다. 숫자는 요인 자체의 값이 아닙니다.</span>
            </div>
            <div className="spf-reason spf-reason-head" aria-hidden="true">
              <span>요인</span><span>방향</span><span style={{ textAlign: 'right' }}>영향</span>
            </div>
            {parsedReasons.map((r, i) => (
              <div key={i} className="spf-reason">
                <span style={{ fontSize: 14, color: 'var(--text)', minWidth: 0 }}>{r.label}</span>
                <span className="v2-nowrap" style={{ fontSize: 13, fontWeight: 600, color: TONE_COLOR[r.tone] }}>{TONE_TAG[r.tone]}</span>
                <span className="v2-nowrap" style={{ ...MONO, textAlign: 'right', fontSize: 15, fontWeight: 600, color: TONE_COLOR[r.tone] }}>{r.value ?? ''}</span>
              </div>
            ))}
          </Card>
        )}
      </div>

      {/* 점수 + 기간별 적중률 */}
      <div className="spf-grid" style={gridCols('1fr 1.4fr')}>
        <Card style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <h2 className="spf-h">점수</h2>
            <span className="v2-nowrap" style={{ fontSize: 13, fontWeight: 600, borderRadius: 999, padding: '4px 12px', background: 'var(--seg-active)', color: 'var(--text)' }}>
              상태 {flowLabel}
            </span>
          </div>
          {[
            { label: '하락 위험', hint: '높을수록 하락 신호', score: bearish, color: 'var(--warn)', numColor: 'var(--text)' },
            { label: '반등 기대', hint: '높을수록 상승 신호', score: bullish, color: 'var(--up)', numColor: 'var(--up)' },
          ].map(b => (
            <div key={b.label} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: 14 }}>
                <span style={{ color: 'var(--text-2)' }}>{b.label} <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{b.hint}</span></span>
                <span style={{ ...MONO, fontWeight: 600, fontSize: isMobile ? 18 : 20, color: b.numColor }}>{b.score}</span>
              </div>
              <div aria-hidden="true" style={{ height: 10, borderRadius: 999, background: 'var(--seg-active)' }}>
                <div style={{ width: `${b.score}%`, minWidth: b.score > 0 ? 4 : 0, height: '100%', borderRadius: 999, background: b.color }} />
              </div>
            </div>
          ))}
        </Card>

        {/* 성적표 — 기간별 방향 적중률 (기대=백테스트, 실측=운영 누적) */}
        <Card style={{ padding: '18px 20px 14px' }}>
          <h2 className="spf-h" style={{ marginBottom: 6 }}>방향 적중률 <small>기간별</small></h2>
          <div className="spf-hit spf-hit-head">
            <span>기간</span><span style={{ textAlign: 'right' }}>기대</span><span style={{ textAlign: 'right' }}>실측</span><span style={{ textAlign: 'right' }}>표본</span>
          </div>
          {['7', '14', '30', '60'].map(h => {
            const s = predData?.stats?.[h]
            const hasReal = s?.realized != null
            const good = hasReal && s!.realized! >= s!.expected
            const color = !hasReal ? 'var(--text-3)' : good ? 'var(--ok)' : 'var(--warn)'
            return (
              <div key={h} className="spf-hit">
                <span style={{ color: 'var(--text-2)' }}>{h}일</span>
                <span className="v2-nowrap" style={{ textAlign: 'right', color: 'var(--text-2)' }}>{s ? `${fmtFixed(s.expected, 1)}%` : '—'}</span>
                <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                  <span className="v2-nowrap" style={{ fontSize: 15, fontWeight: 600, color }}>{hasReal ? `${fmtFixed(s!.realized, 1)}%` : '—'}</span>
                  {hasReal && <span className="v2-nowrap" style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color }}>{good ? '기대 이상' : '기대 미달'}</span>}
                </span>
                <span className="v2-nowrap" style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-3)' }}>{s && s.n > 0 ? `n=${s.n}` : ''}</span>
              </div>
            )
          })}
          <div className="spf-cap" style={{ paddingTop: 8, borderTop: '1px solid var(--line)' }}>
            기대 = 2018~2026 백테스트, 실측 = 운영 누적(방향 커밋만, 중립 제외)
          </div>
        </Card>
      </div>

      {/* OI · 펀딩비 */}
      <div className="spf-grid">
        <Card style={{ padding: '16px 20px 6px' }}>
          {/* 예측 시계가 아니라 최근 포지션 관측 창(3일/7일 룩백) */}
          <h2 className="spf-h" style={{ marginBottom: 6 }}>미결제약정(OI) <small>최근 포지션 흐름</small></h2>
          <div className="v2-list">
            {/* Bybit OI는 BTC 개수 → USD 환산(oi × BTC가격) 후 10억 단위 표시 */}
            <div className="v2-row"><span>현재 OI</span><span style={{ color: 'var(--text)' }}>{current?.oi && current?.price ? `$${fmtFixed(current.oi * current.price / 1e9, 2)}B` : '—'}</span></div>
            <div className="v2-row"><span>3일 변화</span><span style={{ color: oi3.color }}>{oi3.text}</span></div>
            <div className="v2-row"><span>7일 변화</span><span style={{ color: oi7.color }}>{oi7.text}</span></div>
            <div className="v2-row"><span>연속 상승</span><span style={{ color: 'var(--text)' }}>{current ? `${current.oi_consecutive_up}일` : '—'}</span></div>
          </div>
        </Card>
        <Card style={{ padding: '16px 20px 6px' }}>
          <h2 className="spf-h" style={{ marginBottom: 6 }}>펀딩비(FR) <small>최근 펀딩 쏠림</small></h2>
          <div className="v2-list">
            <div className="v2-row"><span>현재 펀딩비</span><span style={{ color: frColor }}>{frPct(current?.fr)}</span></div>
            <div className="v2-row"><span>3일 누적</span><span style={{ color: 'var(--text)' }}>{frPct(current?.cum_fr_3d)}</span></div>
            <div className="v2-row"><span>7일 누적</span><span style={{ color: 'var(--text)' }}>{frPct(current?.cum_fr_7d)}</span></div>
            <div className="v2-row"><span>흐름 유형</span><span style={{ color: 'var(--text)', fontFamily: 'var(--font-sans)' }}>{current ? flowLabel : '—'}</span></div>
          </div>
        </Card>
      </div>

      {/* 점수 추이 + 유사 패턴 */}
      <div className="spf-grid" style={gridCols('1.4fr 1fr')}>
        {chartData.length > 0 && (
          <Card style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 10 }}>
              <h2 className="spf-h">점수 추이 <small>30일</small></h2>
              <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--text-2)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span aria-hidden="true" style={{ width: 14, height: 2, background: 'var(--warn)' }} />하락 위험</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span aria-hidden="true" style={{ width: 14, height: 2, background: 'var(--up)' }} />반등 기대</span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData}>
                <XAxis dataKey="date" tick={{ fill: C.text3, fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: C.text3, fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}
                  labelStyle={{ color: C.text2 }}
                />
                <ReferenceLine y={70} stroke={C.text3} strokeDasharray="3 3" />
                <Line type="monotone" dataKey="bearish" stroke={C.warn} dot={false} strokeWidth={2} name="하락위험" />
                <Line type="monotone" dataKey="bullish" stroke={C.up} dot={false} strokeWidth={2} name="반등기대" />
              </LineChart>
            </ResponsiveContainer>
            <span className="spf-cap">점선 70 — 이 위로 올라가면 경계</span>
          </Card>
        )}

        {similar_patterns.length > 0 && (
          <Card style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <h2 className="spf-h">비슷했던 과거 <small>유사 패턴 TOP {similar_patterns.length}</small></h2>
            {similar_patterns.map((p, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                  <span className="v2-nowrap" style={{ ...MONO, fontSize: 18, fontWeight: 600 }}>{p.date}</span>
                  <span className="v2-nowrap" style={{ fontSize: 13, color: 'var(--text-2)' }}>
                    유사도 <span style={{ ...MONO, fontWeight: 600, color: 'var(--text)' }}>{p.similarity}%</span>
                  </span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '6px 10px', background: 'var(--bg-inset)', borderRadius: 10, padding: '10px 12px', minHeight: 44, boxSizing: 'border-box' }}>
                  <span style={{ fontSize: 13, color: 'var(--text-2)' }}>당시 흐름 <span style={{ color: 'var(--text)', fontWeight: 600 }}>{FLOW_LABELS[p.flow] || p.flow}</span></span>
                  <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
                    이후 3일 <span className="v2-nowrap" style={{ ...MONO, fontSize: 15, fontWeight: 600, color: changeColor(p.change_3d_pct) }}>
                      {changeArrow(p.change_3d_pct)} {fmtSignedPct(p.change_3d_pct)}
                    </span>
                  </span>
                </div>
              </div>
            ))}
          </Card>
        )}
      </div>

      {/* 최근 예측 기록 */}
      {predData && predData.predictions.length > 0 && (
        <Card style={{ padding: '16px 20px 14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: '8px 16px', paddingBottom: 8 }}>
            <h2 className="spf-h">최근 예측 기록 <small>판정: 7/14/30/60일</small></h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontSize: 12, color: 'var(--text-2)' }}>
              <span><span style={{ color: C.ok }}>✓</span> 적중</span>
              <span><span style={{ color: C.warn }}>✗</span> 빗나감</span>
              <span>– 중립</span>
              <span>· 대기(아직 기간이 안 지남)</span>
            </div>
          </div>
          {isMobile ? (
            predData.predictions.slice(0, 10).map((p, i) => (
              <div key={i} className="spf-log-block">
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                  <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                    <span style={{ ...MONO, fontSize: 14, color: 'var(--text-2)' }}>{p.date}</span>
                    <span className="v2-nowrap" style={{ fontSize: 15, fontWeight: 600, color: TONE_COLOR[dirTone(p.direction)] }}>{dirArrow(p.direction)} {p.direction}</span>
                  </span>
                  <span className="v2-nowrap" style={{ fontSize: 13, color: 'var(--text-3)' }}>신뢰도 <span style={{ ...MONO, color: 'var(--text-2)' }}>{p.confidence}%</span></span>
                </div>
                <div className="spf-log-cells">
                  {HISTORY_HORIZONS.map(({ label, field }) => {
                    const meta = getHorizonResultMeta(p[field])
                    return (
                      <div key={field} className="spf-log-cell">
                        <span style={{ ...MONO, fontSize: 12, color: 'var(--text-3)' }}>{label}</span>
                        <span className="v2-nowrap" style={{ fontSize: 13, fontWeight: 600, color: meta.color }}>{meta.symbol} {meta.text}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
          ) : (
            <div className="spf-log-scroll">
              <div className="spf-log-row spf-log-head">
                <span>날짜</span><span>방향</span><span style={{ textAlign: 'right' }}>신뢰도</span>
                {HISTORY_HORIZONS.map(({ label }) => <span key={label}>{label} 후</span>)}
              </div>
              {predData.predictions.slice(0, 10).map((p, i) => (
                <div key={i} className="spf-log-row">
                  <span style={{ ...MONO, fontSize: 14, color: 'var(--text-2)' }}>{p.date}</span>
                  <span className="v2-nowrap" style={{ fontSize: 14, fontWeight: 600, color: TONE_COLOR[dirTone(p.direction)] }}>{dirArrow(p.direction)} {p.direction}</span>
                  <span style={{ ...MONO, textAlign: 'right', fontSize: 14, color: 'var(--text-2)' }}>{p.confidence}%</span>
                  {HISTORY_HORIZONS.map(({ label, field }) => {
                    const meta = getHorizonResultMeta(p[field])
                    return (
                      <span key={field} className="v2-nowrap" aria-label={`${label} ${meta.text}`} style={{ fontSize: 13, fontWeight: 600, color: meta.color }}>
                        {meta.symbol} {meta.text}
                      </span>
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

    </div>
  )
}
