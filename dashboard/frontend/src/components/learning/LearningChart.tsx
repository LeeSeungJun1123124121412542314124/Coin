import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CandlestickSeries, CrosshairMode, HistogramSeries, LineSeries, LineStyle, PriceScaleMode, createChart, createSeriesMarkers } from 'lightweight-charts'
import type { IChartApi, IPriceLine, ISeriesApi, ISeriesMarkersPluginApi, LineWidth, SeriesType, Time } from 'lightweight-charts'
import { getChart, getLive, putSettings } from '../../lib/learningApi.ts'
import type { ChartResponse, Interval, LearningSettings, Structure } from '../../lib/learningApi.ts'
import { C, changeArrow, changeColor, softBg } from '../../lib/theme.ts'
import { Card } from '../shared/Card'
import LastUpdated from '../shared/LastUpdated'
import { sameLiveShape, toCandleSeries, toCloudBands, toLineSeries, toPivotLine, toSec, toWyckoffMarkers, withLive } from './learningChartData.ts'
import { chartHeight, maColor, paneLayout } from './indicatorPanes.ts'
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

// 보조 지표 칩 — 서버 설정의 enabled를 바꾼다 (겹침: 이동평균·볼린저 / 아래 칸: 거래량·RSI·MACD)
type SettingKey = 'ma' | 'bb' | 'volume' | 'rsi' | 'macd'
const SETTING_CHIPS: [SettingKey, string][] = [['ma', '이동평균'], ['bb', '볼린저'], ['volume', '거래량'], ['rsi', 'RSI'], ['macd', 'MACD']]

// 실시간 봉 조회 주기
const LIVE_POLL_MS = 15_000

const BASE_HEIGHT = 460
const PANE_HEIGHT = 110

// 차트 잠금 — 잠금 여부와 잠근 화면(확대 상태)을 브라우저에 저장해 앱을 다시 열어도 유지한다
// time은 모든 종목·시간봉에 똑같이 쓰는 가로 범위(마지막 캔들 기준 봉 위치 — 새 봉이 생겨도 최신 쪽에 붙어 있게)
// prices는 가격축을 손으로 늘렸을 때만 종목|시간봉별로 저장하는 세로 범위(가격대가 서로 달라 함께 쓸 수 없다)
const LOCK_KEY = 'learning-chart-lock'
interface LockStore {
  locked: boolean
  time: { from: number; to: number } | null
  prices: Record<string, { from: number; to: number }>
}
const readLock = (): LockStore => {
  try {
    const s = JSON.parse(localStorage.getItem(LOCK_KEY) ?? '')
    return { locked: !!s.locked, time: s.time ?? null, prices: s.prices ?? {} }
  } catch {
    return { locked: false, time: null, prices: {} }
  }
}

const lineOptions = (color: string, lineWidth: LineWidth, lineStyle: LineStyle = LineStyle.Solid) => ({
  color, lineWidth, lineStyle,
  priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
})

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
  const rangeLinesRef = useRef<IPriceLine[]>([])
  // 보조 지표 시리즈 — 데이터가 바뀔 때마다 지우고 다시 만든다
  const indSeriesRef = useRef<ISeriesApi<SeriesType>[]>([])
  // 마지막으로 fitContent 한 종목|시간봉 — 같은 대상 재조회(칩·폼 저장)에서는 줌을 유지한다
  const fitKeyRef = useRef('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [logScale, setLogScale] = useState(false)
  const [lock, setLock] = useState(readLock)
  // 칩 낙관적 상태 — 만들 때의 차트 데이터(base)에만 유효하다. 새 데이터가 오면 서버 값이 우선
  const [pending, setPending] = useState<{ base: ChartResponse | null; map: Partial<Record<SettingKey, boolean>> }>({ base: null, map: {} })
  const [chipError, setChipError] = useState<string | null>(null)
  // 종목·시간봉이 바뀌면 칩 오류 메시지를 지운다
  const [errorKey, setErrorKey] = useState(`${symbol}|${interval}`)
  if (errorKey !== `${symbol}|${interval}`) {
    setErrorKey(`${symbol}|${interval}`)
    setChipError(null)
  }
  const [shown, setShown] = useState<Record<IndicatorKey, boolean>>({ ichimoku: true, zigzag: true, fib: true })
  const [showRange, setShowRange] = useState(true)

  const load = useMemo(() => (ready ? () => getChart(symbol, interval) : null), [ready, symbol, interval])
  const chart = useLoader(load)
  const data = chart.data
  const reload = chart.reload
  // 실시간 조회 성공 시각 — 만들 때의 차트 데이터(base)에만 유효하다 (새로 불러오면 불러온 시각이 더 늦다)
  const [liveOk, setLiveOk] = useState<{ base: ChartResponse; at: Date } | null>(null)
  const lastLiveAt = liveOk && liveOk.base === data ? liveOk.at : null
  const updatedAt = lastLiveAt && chart.loadedAt && lastLiveAt > chart.loadedAt ? lastLiveAt : chart.loadedAt
  // 칸 수 — 로딩 중(data=null)에는 직전 값을 유지해 아래 칸 높이가 접혔다 펴지지 않게 한다
  const [paneCount, setPaneCount] = useState(0)
  if (data) {
    const n = paneLayout({ volume: data.settings.indicators.volume.enabled, rsi: !!data.indicators?.rsi, macd: !!data.indicators?.macd }).length
    if (n !== paneCount) setPaneCount(n)
  }

  // 차트 인스턴스 생성·정리 (마운트 시 1회, KrStockChart 패턴)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const c = createChart(el, {
      layout: {
        background: { color: C.surface }, textColor: C.text3, fontSize: 11,
        // 칸 구분선 — 기본 색(#E0E3EB)이 흰색으로 보이는 문제
        panes: { separatorColor: C.border, separatorHoverColor: softBg(C.text, 0.12) },
      },
      grid: { vertLines: { color: C.line }, horzLines: { color: C.line } },
      // 일반 모드: 가로줄이 캔들 종가에 달라붙지 않고 마우스 위치 가격을 그대로 따라감
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: C.line },
      timeScale: { borderColor: C.line },
      width: el.clientWidth,
      height: el.clientHeight || BASE_HEIGHT,
    })
    const addLine = (color: string, lineWidth: LineWidth, lineStyle: LineStyle = LineStyle.Solid) =>
      c.addSeries(LineSeries, lineOptions(color, lineWidth, lineStyle))
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
      rangeLinesRef.current = []
      indSeriesRef.current = []
    }
  }, [])

  // 응답 → 시리즈 반영 (외부 시스템 동기화만 수행)
  useEffect(() => {
    const p = partsRef.current
    if (!p || !data) return
    // 십자선이 떠 있는 채로 데이터를 바꾸면 라이브러리가 예전 선 데이터를 찾다 "Value is null"로 죽는다 — 먼저 십자선을 지운다
    p.chart.clearCrosshairPosition()
    p.candle.setData(toCandleSeries(withLive(data.candles, data.live_candles)))
    p.tenkan.setData(toLineSeries(data.ichimoku, 'tenkan'))
    p.kijun.setData(toLineSeries(data.ichimoku, 'kijun'))
    p.chikou.setData(toLineSeries(data.ichimoku, 'chikou'))
    p.senkouA.setData(toLineSeries(data.ichimoku, 'senkou_a'))
    p.senkouB.setData(toLineSeries(data.ichimoku, 'senkou_b'))
    p.zigzag.setData(toPivotLine(data.pivots))
    p.markers.setMarkers(toWyckoffMarkers(data.wyckoff))

    // 저가 종목도 가격이 뭉개지지 않게 소수 자릿수 조정 (0.001 미만은 8자리·minMove 1e-8)
    const last = data.live_candles.at(-1)?.close ?? data.candles.at(-1)?.close ?? 1
    const precision = last < 0.001 ? 8 : last < 1 ? 6 : last < 100 ? 4 : 2
    p.candle.applyOptions({ priceFormat: { type: 'price', precision, minMove: 10 ** -precision } })
    p.chart.applyOptions({ timeScale: { timeVisible: isIntraday(interval) } })
    const fitKey = `${symbol}|${interval}`
    if (fitKeyRef.current !== fitKey) {
      fitKeyRef.current = fitKey
      // 잠금 중이면 잠근 가로 범위를 어느 종목·시간봉에나 그대로 적용, 봉 수가 모자라 범위가 첫 캔들 앞에서 시작하면 전체 맞춤
      const saved = readLock()
      const lastIndex = data.candles.length - 1
      const time = saved.locked && saved.time && lastIndex + saved.time.from >= 0 ? saved.time : null
      if (time) p.chart.timeScale().setVisibleLogicalRange({ from: lastIndex + time.from, to: lastIndex + time.to })
      else p.chart.timeScale().fitContent()
      // 가격축 — 이 종목|시간봉으로 저장된 범위가 있으면 복원, 없으면 자동 맞춤(앞 종목에서 손으로 늘린 범위가 남지 않게)
      const price = saved.locked ? saved.prices[fitKey] : undefined
      if (price) p.candle.priceScale().setVisibleRange(price)
      else p.candle.priceScale().setAutoScale(true)
    }
  }, [data, symbol, interval])

  // 실시간 봉 조회 — 15초마다, 화면이 보일 때만. 구성이 같으면 마지막 봉만 갱신(데이터 상태를 바꾸지 않아 십자선 유지), 새 봉이면 전체 재조회
  useEffect(() => {
    if (!data) return
    let cancelled = false
    const poll = () => {
      if (document.visibilityState !== 'visible') return
      getLive(symbol, interval).then(res => {
        const p = partsRef.current
        if (cancelled || !p) return
        setLiveOk({ base: data, at: new Date() })
        if (sameLiveShape(data.live_candles, res.live_candles)) {
          // 같은 구성이면 마감된 봉은 그대로이고 마지막 봉만 변한다 (update 는 마지막 봉 이후 시각만 받는다)
          const last = res.live_candles.at(-1)
          if (last) p.candle.update(toCandleSeries([last])[0])
        } else {
          reload()
        }
      }, () => { /* 조용히 넘기고 다음 주기에 다시 시도 */ })
    }
    const timer = setInterval(poll, LIVE_POLL_MS)
    const onVisible = () => poll()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [data, symbol, interval, reload])

  // 잠금 반영 — 잠그면 확대·축소와 휠·세로 터치가 꺼져 차트 위에서도 페이지가 스크롤된다. 좌우로 끌어 시간 이동하는 것만 남긴다
  useEffect(() => {
    localStorage.setItem(LOCK_KEY, JSON.stringify(lock))
    partsRef.current?.chart.applyOptions({
      handleScroll: lock.locked ? { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false } : true,
      handleScale: !lock.locked,
      layout: { panes: { enableResize: !lock.locked } },
    })
  }, [lock])

  // 보조 지표 반영 — 기존 시리즈를 지우고(빈 칸은 라이브러리가 정리), 응답에 있는 지표만 다시 그린다
  useEffect(() => {
    const p = partsRef.current
    if (!p) return
    for (const s of indSeriesRef.current) p.chart.removeSeries(s)
    indSeriesRef.current = []
    if (!data) return

    const ind = data.indicators ?? {}
    const addLineAt = (pane: number, color: string, style: LineStyle = LineStyle.Solid, extra: { lastValueVisible?: boolean; autoscaleInfoProvider?: () => { priceRange: { minValue: number; maxValue: number } } } = {}) => {
      const s = p.chart.addSeries(LineSeries, { ...lineOptions(color, 1, style), ...extra }, pane)
      indSeriesRef.current.push(s)
      return s
    }
    const addHistAt = (pane: number, options: { priceFormat?: { type: 'volume' } } = {}) => {
      const s = p.chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false, ...options }, pane)
      indSeriesRef.current.push(s)
      return s
    }

    // 본 칸 겹침 — 이동평균(기간별 색), 볼린저(상·하단 text2, 중단 text3 점선)
    ind.ma?.forEach((m, i) => {
      addLineAt(0, maColor(i)).setData(m.points.map(pt => ({ time: toSec(pt.time), value: pt.value })))
    })
    if (ind.bb) {
      const bb = ind.bb
      const band = (key: 'upper' | 'mid' | 'lower', color: string, style: LineStyle) =>
        addLineAt(0, color, style).setData(bb.map(pt => ({ time: toSec(pt.time), value: pt[key] })))
      band('upper', C.text2, LineStyle.Solid)
      band('mid', C.text3, LineStyle.Dashed)
      band('lower', C.text2, LineStyle.Solid)
    }

    // 아래 칸 — 켜진 순서(거래량 → RSI → MACD)대로 pane 1, 2, 3
    const layout = paneLayout({ volume: data.settings.indicators.volume.enabled, rsi: !!ind.rsi, macd: !!ind.macd })
    for (const { key, index } of layout) {
      if (key === 'volume') {
        addHistAt(index, { priceFormat: { type: 'volume' } }).setData(
          data.candles.map(c => ({
            time: toSec(c.open_time), value: c.volume,
            color: softBg(c.close >= c.open ? C.up : C.down, 0.5),
          })),
        )
      } else if (key === 'rsi' && ind.rsi) {
        // RSI는 세로축을 0~100으로 고정하고 현재 값을 표시
        const line = addLineAt(index, C.violet, LineStyle.Solid, {
          lastValueVisible: true,
          autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
        })
        line.setData(ind.rsi.map(pt => ({ time: toSec(pt.time), value: pt.value })))
        for (const [price, color] of [[70, C.warn], [30, C.ok]] as const) {
          line.createPriceLine({ price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' })
        }
      } else if (key === 'macd' && ind.macd) {
        addHistAt(index).setData(
          ind.macd.map(pt => ({ time: toSec(pt.time), value: pt.hist, color: softBg(pt.hist >= 0 ? C.up : C.down, 0.5) })),
        )
        addLineAt(index, C.info, LineStyle.Solid, { lastValueVisible: true }).setData(ind.macd.map(pt => ({ time: toSec(pt.time), value: pt.macd })))
        addLineAt(index, C.warn, LineStyle.Solid, { lastValueVisible: true }).setData(ind.macd.map(pt => ({ time: toSec(pt.time), value: pt.signal })))
      }
    }

    // 본 칸 높이는 그대로 — stretch 비율을 픽셀 높이(본 칸 460·아래 칸 110)로 맞춘다
    p.chart.panes().forEach((pane, i) => pane.setStretchFactor(i === 0 ? BASE_HEIGHT : PANE_HEIGHT))
  }, [data])

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

  // 구조 범위 가로선 — 칩이 켜져 있을 때만, 값이 있는 것만 지우고 다시 만든다
  useEffect(() => {
    const p = partsRef.current
    if (!p) return
    for (const line of rangeLinesRef.current) p.candle.removePriceLine(line)
    const st = data?.structure
    const lines: [string, number | null | undefined, string][] = st ? [
      ['HTF 고점', st.htf.range.high, C.violet],
      ['HTF 저점', st.htf.range.low, C.violet],
      ['LTF 고점', st.ltf.range.high, C.accent],
      ['LTF 저점', st.ltf.range.low, C.accent],
    ] : []
    rangeLinesRef.current = showRange
      ? lines.flatMap(([title, price, color]) => price == null ? [] : [p.candle.createPriceLine({
        price, color, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: true, title,
      })])
      : []
  }, [data, showRange])

  // 가격축 선형/로그 — 오른쪽 가격축 모드만 바꾼다
  useEffect(() => {
    partsRef.current?.chart.priceScale('right').applyOptions({
      mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
    })
  }, [logScale])

  const pendingOf = (key: SettingKey) => (pending.base === data ? pending.map[key] : undefined)
  const isOn = (key: SettingKey) => pendingOf(key) ?? data?.settings.indicators[key].enabled ?? false

  // 칩 — 낙관적으로 바꾸고 저장, 성공하면 차트 재조회, 실패하면 되돌리고 메시지 표시
  const toggleSetting = async (key: SettingKey) => {
    if (!data) return
    const enabled = !isOn(key)
    setChipError(null)
    const prev = pendingOf(key)
    setPending(p => ({ base: data, map: { ...(p.base === data ? p.map : {}), [key]: enabled } }))
    try {
      await putSettings({ indicators: { [key]: { enabled } } })
      chart.reload()
    } catch (e) {
      // 토글 전 상태(없으면 서버 값)로 정확히 복원
      setPending(p => ({ base: data, map: { ...(p.base === data ? p.map : {}), [key]: prev } }))
      setChipError(errorText(e))
    }
  }

  // 잠금 토글 — 잠글 때 지금 보이는 가로 범위를 저장하고, 가격축을 손으로 늘렸으면 이 종목|시간봉의 세로 범위도 저장한다
  const toggleLock = () => {
    const p = partsRef.current
    if (lock.locked || !p || !data) {
      setLock(l => ({ ...l, locked: false }))
      return
    }
    const range = p.chart.timeScale().getVisibleLogicalRange()
    const lastIndex = data.candles.length - 1
    const scale = p.candle.priceScale()
    const price = scale.options().autoScale ? null : scale.getVisibleRange()
    const prices = { ...lock.prices }
    if (price) prices[`${symbol}|${interval}`] = price
    else delete prices[`${symbol}|${interval}`]
    setLock({
      locked: true,
      time: range ? { from: range.from - lastIndex, to: range.to - lastIndex } : lock.time,
      prices,
    })
  }

  // 켜진 보조 지표 범례 — 서버 응답(켜진 지표만 존재)과 설정 기간 기준 (거래량은 막대로 명확해 제외)
  const indicatorLegend: [string, string][] = []
  if (data?.indicators) {
    const { ma, bb, rsi, macd } = data.settings.indicators
    data.indicators.ma?.forEach((m, i) => indicatorLegend.push([`${ma.type.toUpperCase()} ${m.period}`, maColor(i)]))
    if (data.indicators.bb) indicatorLegend.push([`볼린저 ${bb.period}·${bb.stddev}`, C.text2])
    if (data.indicators.rsi) indicatorLegend.push([`RSI ${rsi.period}`, C.violet])
    if (data.indicators.macd) {
      indicatorLegend.push([`MACD ${macd.fast}·${macd.slow}`, C.info], [`시그널 ${macd.signal}`, C.warn])
    }
  }

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
      <LastUpdated timestamp={updatedAt} />
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
        <div className="tap-seg" style={segGroupStyle} role="group" aria-label="시간봉">
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
          <button style={toggleStyle(showRange)} aria-pressed={showRange} onClick={() => setShowRange(v => !v)}>
            구조 범위
          </button>
          {SETTING_CHIPS.map(([key, label]) => (
            <button key={key} style={toggleStyle(isOn(key))} aria-pressed={isOn(key)} disabled={!data}
              onClick={() => toggleSetting(key)}>
              {label}
            </button>
          ))}
        </div>
        <div className="tap-seg" style={segGroupStyle} role="group" aria-label="가격축">
          {([['선형', false], ['로그', true]] as const).map(([label, log]) => (
            <button key={label} style={segButtonStyle(logScale === log)} aria-pressed={logScale === log} onClick={() => setLogScale(log)}>
              {label}
            </button>
          ))}
        </div>
        <button style={toggleStyle(lock.locked)} aria-pressed={lock.locked} disabled={!data} onClick={toggleLock}
          title="잠그면 차트 위에서도 페이지가 스크롤되고, 지금 확대 상태가 저장됩니다">
          차트 잠금
        </button>
        <button style={toggleStyle(settingsOpen)} disabled={!data} onClick={() => setSettingsOpen(o => !o)}>
          지표 설정
        </button>
        {chipError && <span style={errorStyle}>{chipError}</span>}
      </div>

      {settingsOpen && data && (
        <SettingsForm
          settings={data.settings}
          isOn={isOn}
          onSaved={() => chart.reload()}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        <Card style={{ flex: '3 1 520px', minWidth: 0 }}>
          <div style={{ position: 'relative', height: chartHeight(BASE_HEIGHT, paneCount, PANE_HEIGHT) }}>
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
            {showRange && data?.structure && (
              <div title={data.structure.reasons.join('\n')} style={{
                position: 'absolute', top: 6, left: 8, zIndex: 2, padding: '2px 6px', borderRadius: 4,
                background: softBg(C.surface, 0.85), color: 'var(--text-2)', fontSize: '0.75rem', pointerEvents: 'auto',
              }}>
                <StructureLine structure={data.structure} interval={interval} />
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 8, fontSize: '0.75rem', color: MUTED }}>
            {[...LEGEND, ...indicatorLegend].map(([label, color]) => (
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
const STRUCTURE_LABELS = { bullish: '매수 우위', neutral: '중립', bearish: '매도 우위' } as const
const signed = (n: number) => (n === 0 ? '0' : `${n > 0 ? '+' : '−'}${Math.abs(n)}`)

/** 차트 왼쪽 위 한 줄: HTF·LTF 기여 점수와 합계 */
function StructureLine({ structure: st, interval }: { structure: Structure; interval: Interval }) {
  const dir = st.label === 'bullish' ? 1 : st.label === 'bearish' ? -1 : 0
  const htf = st.htf_interval ? `HTF(${INTERVAL_LABELS[st.htf_interval]}) ${signed(st.htf_pts)}` : 'HTF 없음 0'
  return (
    <>
      {htf} · LTF({INTERVAL_LABELS[interval]}) {signed(st.ltf_pts)} · 합계{' '}
      <b style={{ color: changeColor(dir) }}>{st.score} {STRUCTURE_LABELS[st.label]}</b>
      {st.bonus !== 0 && ` · 일치 ${signed(st.bonus)}`}
    </>
  )
}

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

// 와이코프·엘리엇(지그재그·피보)·보조 지표 설정 편집 — 저장 후 차트 재조회, 400은 메시지 표시
function SettingsForm({ settings, isOn, onSaved, onClose }: {
  settings: LearningSettings
  isOn: (key: SettingKey) => boolean
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
    ma_type: settings.indicators.ma.type as string,
    ma_periods: settings.indicators.ma.periods.join(', '),
    bb_period: String(settings.indicators.bb.period),
    bb_stddev: String(settings.indicators.bb.stddev),
    rsi_period: String(settings.indicators.rsi.period),
    macd_fast: String(settings.indicators.macd.fast),
    macd_slow: String(settings.indicators.macd.slow),
    macd_signal: String(settings.indicators.macd.signal),
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
  // "보조 지표" 묶음 — 이동평균 종류는 select라 따로 둔다
  const indFields: [keyof typeof form, string][] = [
    ['ma_periods', '이동평균 기간 (쉼표 구분)'],
    ['bb_period', '볼린저 기간'],
    ['bb_stddev', '볼린저 표준편차'],
    ['rsi_period', 'RSI 기간'],
    ['macd_fast', 'MACD 빠른'],
    ['macd_slow', 'MACD 느린'],
    ['macd_signal', 'MACD 시그널'],
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
        // enabled는 칩이 방금 저장한 값을 덮어쓰지 않게 현재 칩 상태를 보낸다
        indicators: {
          ma: {
            ...settings.indicators.ma, enabled: isOn('ma'),
            type: form.ma_type === 'ema' ? 'ema' : 'sma',
            periods: form.ma_periods.split(',').map(s => s.trim()).filter(Boolean).map(Number),
          },
          bb: { ...settings.indicators.bb, enabled: isOn('bb'), period: Number(form.bb_period), stddev: Number(form.bb_stddev) },
          rsi: { ...settings.indicators.rsi, enabled: isOn('rsi'), period: Number(form.rsi_period) },
          macd: {
            ...settings.indicators.macd, enabled: isOn('macd'),
            fast: Number(form.macd_fast), slow: Number(form.macd_slow), signal: Number(form.macd_signal),
          },
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
      <div style={{ margin: '14px 0 6px', fontSize: '0.78rem', fontWeight: 600, color: MUTED }}>보조 지표</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.75rem', color: MUTED }}>
          이동평균 종류
          <select style={inputStyle} value={form.ma_type} onChange={e => setForm(f => ({ ...f, ma_type: e.target.value }))}>
            <option value="sma">SMA (단순)</option>
            <option value="ema">EMA (지수)</option>
          </select>
        </label>
        {indFields.map(([key, label]) => (
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
