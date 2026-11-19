import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CandlestickSeries, LineSeries, LineStyle, PriceScaleMode, createChart, createSeriesMarkers } from 'lightweight-charts'
import type { IChartApi, IPriceLine, ISeriesApi, ISeriesMarkersPluginApi, LineWidth, Time } from 'lightweight-charts'
import { getChart, putSettings } from '../../lib/learningApi.ts'
import type { ChartResponse, Interval, LearningSettings } from '../../lib/learningApi.ts'
import { C, changeArrow, changeColor, softBg } from '../../lib/theme.ts'
import { Card } from '../shared/Card'
import { toCandleSeries, toCloudBands, toLineSeries, toPivotLine, toWyckoffMarkers } from './learningChartData.ts'
import { IchimokuCloud } from './ichimokuCloud.ts'
import {
  DIM, ICHIMOKU_FIELDS, INTERVALS, INTERVAL_LABELS, MUTED, UNDECIDABLE, buttonStyle, errorStyle, errorText, fmtBarTime, fmtPrice,
  inputStyle, isIntraday, noteStyle, segButtonStyle, segGroupStyle, titleStyle, toggleStyle, useLoader,
} from './learningShared.ts'

// 차트 색 — lightweight-charts는 CSS 변수를 못 쓰므로 theme.ts의 hex(C)를 쓴다
const COLORS = {
  up: C.up,
  down: C.down,
  tenkan: C.warn,
  kijun: C.violet,
  chikou: C.text3,
  senkouA: softBg(C.up, 0.6),
  senkouB: softBg(C.down, 0.6),
  zigzag: softBg(C.text, 0.85),
  fib: C.text3,
}

const LEGEND: [string, string][] = [
  ['전환선', COLORS.tenkan],
  ['기준선', COLORS.kijun],
  ['후행스팬', COLORS.chikou],
  ['선행스팬 A', COLORS.senkouA],
  ['선행스팬 B', COLORS.senkouB],
  ['지그재그', COLORS.zigzag],
  ['피보나치', COLORS.fib],
]

// 지표 표시 토글 — 일목(전환·기준·후행·선행·구름) / 지그재그 / 피보나치
type IndicatorKey = 'ichimoku' | 'zigzag' | 'fib'
const INDICATORS: [IndicatorKey, string][] = [['ichimoku', '일목균형표'], ['zigzag', '지그재그'], ['fib', '피보나치']]

interface ChartParts {
  chart: IChartApi
  candle: ISeriesApi<'Candlestick'>
  tenkan: ISeriesApi<'Line'>
  kijun: ISeriesApi<'Line'>
  chikou: ISeriesApi<'Line'>
  senkouA: ISeriesApi<'Line'>
  senkouB: ISeriesApi<'Line'>
  zigzag: ISeriesApi<'Line'>
  cloud: IchimokuCloud
  markers: ISeriesMarkersPluginApi<Time>
}

interface LearningChartProps {
  symbol: string
  interval: Interval
  onIntervalChange: (interval: Interval) => void
  // 백필 대기 중에는 조회하지 않고, 완료/실패로 바뀌면 조회한다
  ready: boolean
  // 오른쪽 열에서 일목 상태 카드 아래에 붙는 영역 (모의 주문)
  aside?: ReactNode
}

export function LearningChart({ symbol, interval, onIntervalChange, ready, aside }: LearningChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const partsRef = useRef<ChartParts | null>(null)
  const fibLinesRef = useRef<IPriceLine[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [logScale, setLogScale] = useState(false)
  const [shown, setShown] = useState<Record<IndicatorKey, boolean>>({ ichimoku: true, zigzag: true, fib: true })

  const load = useMemo(() => (ready ? () => getChart(symbol, interval) : null), [ready, symbol, interval])
  const chart = useLoader(load)
  const data = chart.data

  // 차트 인스턴스 생성·정리 (마운트 시 1회, KrStockChart 패턴)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const c = createChart(el, {
      layout: { background: { color: C.surface }, textColor: C.text3, fontSize: 11 },
      grid: { vertLines: { color: C.line }, horzLines: { color: C.line } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: C.line },
      timeScale: { borderColor: C.line },
      width: el.clientWidth,
      height: el.clientHeight || 460,
    })
    const addLine = (color: string, lineWidth: LineWidth, lineStyle: LineStyle = LineStyle.Solid) =>
      c.addSeries(LineSeries, {
        color, lineWidth, lineStyle,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      })
    const candle = c.addSeries(CandlestickSeries, {
      upColor: COLORS.up, downColor: COLORS.down,
      borderUpColor: COLORS.up, borderDownColor: COLORS.down,
      wickUpColor: COLORS.up, wickDownColor: COLORS.down,
    })
    const cloud = new IchimokuCloud()
    candle.attachPrimitive(cloud)
    partsRef.current = {
      chart: c,
      candle,
      senkouA: addLine(COLORS.senkouA, 1),
      senkouB: addLine(COLORS.senkouB, 1),
      tenkan: addLine(COLORS.tenkan, 1),
      kijun: addLine(COLORS.kijun, 2),
      chikou: addLine(COLORS.chikou, 1, LineStyle.Dotted),
      zigzag: addLine(COLORS.zigzag, 2),
      cloud,
      markers: createSeriesMarkers(candle, []),
    }

    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      c.applyOptions({ width, height })
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      c.remove()
      partsRef.current = null
      fibLinesRef.current = []
    }
  }, [])

  // 응답 → 시리즈 반영 (외부 시스템 동기화만 수행)
  useEffect(() => {
    const p = partsRef.current
    if (!p || !data) return
    p.candle.setData(toCandleSeries(data.candles))
    p.tenkan.setData(toLineSeries(data.ichimoku, 'tenkan'))
    p.kijun.setData(toLineSeries(data.ichimoku, 'kijun'))
    p.chikou.setData(toLineSeries(data.ichimoku, 'chikou'))
    p.senkouA.setData(toLineSeries(data.ichimoku, 'senkou_a'))
    p.senkouB.setData(toLineSeries(data.ichimoku, 'senkou_b'))
    p.zigzag.setData(toPivotLine(data.pivots))
    p.markers.setMarkers(toWyckoffMarkers(data.wyckoff))

    // 저가 종목도 가격이 뭉개지지 않게 소수 자릿수 조정 (0.001 미만은 8자리·minMove 1e-8)
    const last = data.candles.at(-1)?.close ?? 1
    const precision = last < 0.001 ? 8 : last < 1 ? 6 : last < 100 ? 4 : 2
    p.candle.applyOptions({ priceFormat: { type: 'price', precision, minMove: 10 ** -precision } })
    p.chart.applyOptions({ timeScale: { timeVisible: isIntraday(interval) } })
    p.chart.timeScale().fitContent()
  }, [data, interval])

  // 지표 표시 토글 반영 — 구름은 빈 데이터로 지우고, 피보나치는 가격선을 지우고 다시 만든다 (줌 위치는 건드리지 않음)
  useEffect(() => {
    const p = partsRef.current
    if (!p) return
    for (const line of [p.tenkan, p.kijun, p.chikou, p.senkouA, p.senkouB]) line.applyOptions({ visible: shown.ichimoku })
    p.zigzag.applyOptions({ visible: shown.zigzag })
    p.cloud.setData(data && shown.ichimoku ? toCloudBands(data.ichimoku) : [])
    for (const line of fibLinesRef.current) p.candle.removePriceLine(line)
    fibLinesRef.current = data && shown.fib
      ? data.fib.map(f => p.candle.createPriceLine({
        price: f.price, color: COLORS.fib, lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: `피보 ${f.level}`,
      }))
      : []
  }, [data, shown])

  // 가격축 선형/로그 — 오른쪽 가격축 모드만 바꾼다
  useEffect(() => {
    partsRef.current?.chart.priceScale('right').applyOptions({
      mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
    })
  }, [logScale])

  const overlay = !ready
    ? '백필 중입니다. 완료되면 차트를 불러옵니다.'
    : chart.error
      ? chart.error
      : !data
        ? '차트 불러오는 중...'
        : data.candles.length === 0
          ? '캔들 데이터가 없습니다. 백필 상태를 확인하세요.'
          : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
        <div style={segGroupStyle} role="group" aria-label="시간봉">
          {INTERVALS.map(i => (
            <button key={i} style={segButtonStyle(interval === i)} aria-pressed={interval === i} onClick={() => onIntervalChange(i)}>
              {INTERVAL_LABELS[i]}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {INDICATORS.map(([key, label]) => (
            <button key={key} style={toggleStyle(shown[key])} aria-pressed={shown[key]}
              onClick={() => setShown(s => ({ ...s, [key]: !s[key] }))}>
              {label}
            </button>
          ))}
        </div>
        <div style={segGroupStyle} role="group" aria-label="가격축">
          {([['선형', false], ['로그', true]] as const).map(([label, log]) => (
            <button key={label} style={segButtonStyle(logScale === log)} aria-pressed={logScale === log} onClick={() => setLogScale(log)}>
              {label}
            </button>
          ))}
        </div>
        <button style={toggleStyle(settingsOpen)} disabled={!data} onClick={() => setSettingsOpen(o => !o)}>
          지표 설정
        </button>
      </div>

      {settingsOpen && data && (
        <SettingsForm
          settings={data.settings}
          onSaved={() => chart.reload()}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        <Card style={{ flex: '3 1 520px', minWidth: 0 }}>
          <div style={{ position: 'relative', height: 460 }}>
            {overlay && (
              <div style={{
                position: 'absolute', inset: 0, zIndex: 5, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: softBg(C.surface, 0.85), color: chart.error ? 'var(--danger)' : MUTED, fontSize: '0.85rem',
                padding: 16, textAlign: 'center',
              }}>
                {overlay}
              </div>
            )}
            <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 8, fontSize: '0.72rem', color: MUTED }}>
            {LEGEND.map(([label, color]) => (
              <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 12, height: 2, background: color, display: 'inline-block' }} />
                {label}
              </span>
            ))}
            <span>구름: 빨강 양운 · 파랑 음운</span>
            <span>마커: ▲ 스프링 · ▼ 업스러스트</span>
          </div>
        </Card>

        <div style={{ flex: '1 1 320px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {data ? (
            <StateSummary data={data} withHour={isIntraday(interval)} />
          ) : (
            <Card><h3 style={titleStyle}>{symbol} 일목 상태</h3><div style={noteStyle}>차트를 불러오면 표시됩니다.</div></Card>
          )}
          {aside}
        </div>
      </div>
    </div>
  )
}

// 일목 값 → 상승(+1)·하락(-1)·중립(0) 방향. 구름 안·교차 없음·판단 불가는 중립
const BULLISH_VALUES = new Set(['above', 'golden', 'bullish'])
const BEARISH_VALUES = new Set(['below', 'dead', 'bearish'])
const tone = (v: string | null) => (v !== null && BULLISH_VALUES.has(v) ? 1 : v !== null && BEARISH_VALUES.has(v) ? -1 : 0)

// 현재 일목 상태·와이코프 박스 요약 (값 null은 판단 불가)
function StateSummary({ data, withHour }: { data: ChartResponse; withHour: boolean }) {
  const box = data.wyckoff.current_box
  const row = { display: 'flex', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--line)', fontSize: '0.82rem' } as const
  return (
    <Card>
      <h3 style={titleStyle}>일목 상태</h3>
      <div>
        {ICHIMOKU_FIELDS.map(f => {
          const v = data.state[f.key]
          const t = tone(v)
          return (
            <div key={f.key} style={row}>
              <span style={{ color: DIM }}>{f.label}</span>
              <b style={{ color: changeColor(t) }}>{changeArrow(t)} {v === null ? UNDECIDABLE : f.options[v]}</b>
            </div>
          )
        })}
        <div style={{ ...row, borderBottom: 'none', flexDirection: 'column', gap: 4 }}>
          <span style={{ color: DIM }}>와이코프 박스</span>
          <span style={{ color: MUTED }}>
            {box
              ? `고점 ${fmtPrice(box.high)} · 저점 ${fmtPrice(box.low)} (${fmtBarTime(box.start, withHour)} ~ ${fmtBarTime(box.end, withHour)})`
              : '현재 박스 없음'}
          </span>
          <span style={{ color: DIM, fontSize: '0.75rem' }}>후보 {data.wyckoff.candidates.length}개 · 피벗 {data.pivots.length}개</span>
        </div>
      </div>
    </Card>
  )
}

// 와이코프·엘리엇(지그재그·피보) 설정 편집 — 저장 후 차트 재조회, 400은 메시지 표시
function SettingsForm({ settings, onSaved, onClose }: {
  settings: LearningSettings
  onSaved: () => void
  onClose: () => void
}) {
  const [form, setForm] = useState({
    n: String(settings.wyckoff.n),
    width_pct: String(settings.wyckoff.width_pct),
    vol_mult: String(settings.wyckoff.vol_mult),
    threshold_1h: String(settings.elliott.threshold_1h),
    threshold_4h: String(settings.elliott.threshold_4h),
    threshold_1d: String(settings.elliott.threshold_1d),
    threshold_1w: String(settings.elliott.threshold_1w),
    threshold_1M: String(settings.elliott.threshold_1M),
    levels: settings.elliott.levels.join(', '),
  })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  const fields: [keyof typeof form, string][] = [
    ['n', '와이코프 박스 봉 수 (n)'],
    ['width_pct', '박스 폭 상한 (%)'],
    ['vol_mult', '거래량 급증 배수'],
    ['threshold_1h', '지그재그 임계값 1시간봉 (%)'],
    ['threshold_4h', '지그재그 임계값 4시간봉 (%)'],
    ['threshold_1d', '지그재그 임계값 일봉 (%)'],
    ['threshold_1w', '지그재그 임계값 주봉 (%)'],
    ['threshold_1M', '지그재그 임계값 월봉 (%)'],
    ['levels', '피보나치 레벨 (쉼표 구분)'],
  ]

  const save = async () => {
    setBusy(true)
    setMessage(null)
    try {
      await putSettings({
        wyckoff: { n: Number(form.n), width_pct: Number(form.width_pct), vol_mult: Number(form.vol_mult) },
        elliott: {
          threshold_1h: Number(form.threshold_1h),
          threshold_4h: Number(form.threshold_4h),
          threshold_1d: Number(form.threshold_1d),
          threshold_1w: Number(form.threshold_1w),
          threshold_1M: Number(form.threshold_1M),
          levels: form.levels.split(',').map(s => s.trim()).filter(Boolean).map(Number),
        },
      })
      setMessage({ ok: true, text: '저장했습니다. 차트를 다시 계산합니다.' })
      onSaved()
    } catch (e) {
      setMessage({ ok: false, text: errorText(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 12, padding: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>
        {fields.map(([key, label]) => (
          <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.75rem', color: MUTED }}>
            {label}
            <input
              style={inputStyle}
              value={form[key]}
              onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        <button style={buttonStyle(!busy)} disabled={busy} onClick={save}>저장</button>
        <button style={toggleStyle(false)} onClick={onClose}>닫기</button>
        {message && <span style={message.ok ? noteStyle : errorStyle}>{message.text}</span>}
      </div>
    </div>
  )
}
