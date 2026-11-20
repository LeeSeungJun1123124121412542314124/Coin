// 리더보드 방향 칸 — 자산별 포지션 방향을 한 줄 글로 요약 (순수 TS)
// 신호 값은 API가 주는 'long' | 'short'. 현금(포지션 없음)은 키가 없거나 null.
export type DirectionTone = 'up' | 'down' | 'flat'

const LABEL: Record<string, string> = { long: '롱', short: '숏' }

export function directionText(
  signals: Record<string, string | null | undefined>,
  order: string[] = ['BTC', 'ETH', 'SOL'],
): { text: string; tone: DirectionTone } {
  // 방향별로 자산을 모은다 (order 순서, 포지션 없는 자산은 뺌)
  const groups: { dir: string; assets: string[] }[] = []
  for (const asset of order) {
    const dir = signals[asset]
    if (dir !== 'long' && dir !== 'short') continue
    const g = groups.find((x) => x.dir === dir)
    if (g) g.assets.push(asset)
    else groups.push({ dir, assets: [asset] })
  }

  if (groups.length === 0) return { text: '관망', tone: 'flat' }
  if (groups.length === 1) {
    const { dir, assets } = groups[0]
    const tone = dir === 'long' ? 'up' : 'down'
    // 모든 종목이 같은 방향이면 "전 종목", 일부면 해당 종목만 나열
    const who = assets.length === order.length ? '전 종목' : assets.join('·')
    return { text: `${who} ${LABEL[dir]}`, tone }
  }
  return { text: groups.map((g) => `${g.assets.join('·')} ${LABEL[g.dir]}`).join(' · '), tone: 'flat' }
}
