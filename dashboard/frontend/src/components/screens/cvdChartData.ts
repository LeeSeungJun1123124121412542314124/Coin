export interface CvdPoint {
  date: string
  cvd: number
  close: number | null
}

export interface CvdChartPoint extends CvdPoint {
  xKey: string
  dateLabel: string
  delta: number
}

function formatCvdDateLabel(date: string) {
  if (/^\d{4}-\d{2}-\d{2}/.test(date)) {
    return date.slice(5, 10)
  }
  return date
}

export function buildCvdChart(points: CvdPoint[], limit = 60): CvdChartPoint[] {
  return points.slice(-limit).map((point, index, pointsInView) => ({
    date: point.date,
    xKey: `${index}:${point.date}`,
    dateLabel: formatCvdDateLabel(point.date),
    cvd: point.cvd,
    close: point.close ?? null,
    delta: index > 0 ? point.cvd - pointsInView[index - 1].cvd : 0,
  }))
}
