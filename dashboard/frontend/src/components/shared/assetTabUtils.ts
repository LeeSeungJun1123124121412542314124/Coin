export type AssetTab = 'coin' | 'kr' | 'us'

export const ASSET_LABELS: Record<AssetTab, string> = {
  coin: '코인',
  kr: '한국',
  us: '미국/환율',
}

function isAssetTab(value: string | null): value is AssetTab {
  return value === 'coin' || value === 'kr' || value === 'us'
}

export function readAssetTab(allowedTabs: readonly AssetTab[] = ['coin', 'kr', 'us']): AssetTab {
  const value = new URLSearchParams(window.location.search).get('asset')
  if (isAssetTab(value) && allowedTabs.includes(value)) return value
  if (value !== null) replaceAssetTab('coin')
  return 'coin'
}

export function replaceAssetTab(asset: AssetTab) {
  const url = new URL(window.location.href)
  url.searchParams.set('asset', asset)
  window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`)
}
