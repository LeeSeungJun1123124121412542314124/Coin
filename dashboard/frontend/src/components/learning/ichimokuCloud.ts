import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp,
} from 'lightweight-charts'

// 일목 구름 채우기 — 선행스팬 A·B 사이를 양운/음운 색으로 칠하는 시리즈 프리미티브 (lightweight-charts v5)
export interface CloudBand {
  time: UTCTimestamp
  top: number
  bottom: number
  bullish: boolean
}

type Target = Parameters<IPrimitivePaneRenderer['draw']>[0]
interface Point { x: number; top: number; bottom: number }

const BULL_FILL = 'rgba(74, 222, 128, 0.16)'
const BEAR_FILL = 'rgba(248, 113, 113, 0.16)'

function fillBand(ctx: CanvasRenderingContext2D, pts: Point[], color: string) {
  if (pts.length < 2) return
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].top)
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].top)
  for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(pts[i].x, pts[i].bottom)
  ctx.closePath()
  ctx.fillStyle = color
  ctx.fill()
}

export class IchimokuCloud implements ISeriesPrimitive<Time> {
  private bands: CloudBand[] = []
  private param: SeriesAttachedParameter<Time, SeriesType> | null = null
  private readonly views: readonly IPrimitivePaneView[]

  constructor() {
    const renderer: IPrimitivePaneRenderer = { draw: target => this.draw(target) }
    // 캔들 아래 레이어에 그린다
    this.views = [{ zOrder: () => 'bottom', renderer: () => renderer }]
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>) {
    this.param = param
  }

  detached() {
    this.param = null
  }

  paneViews() {
    return this.views
  }

  setData(bands: CloudBand[]) {
    this.bands = bands
    this.param?.requestUpdate()
  }

  private draw(target: Target) {
    const p = this.param
    if (!p || this.bands.length < 2) return
    const timeScale = p.chart.timeScale()
    const pts = this.bands.map(b => ({
      x: timeScale.timeToCoordinate(b.time),
      top: p.series.priceToCoordinate(b.top),
      bottom: p.series.priceToCoordinate(b.bottom),
      bullish: b.bullish,
    }))
    target.useMediaCoordinateSpace(({ context }) => {
      // 같은 색이 이어지는 구간마다 다각형 하나. 다음 구간 첫 점을 포함해 교차 지점에서 끊기지 않게 한다
      let start = 0
      for (let i = 1; i <= pts.length; i++) {
        if (i < pts.length && pts[i].bullish === pts[start].bullish) continue
        const seg: Point[] = []
        for (const q of pts.slice(start, Math.min(i + 1, pts.length))) {
          if (q.x !== null && q.top !== null && q.bottom !== null) seg.push({ x: q.x, top: q.top, bottom: q.bottom })
        }
        fillBand(context, seg, pts[start].bullish ? BULL_FILL : BEAR_FILL)
        start = i
      }
    })
  }
}
