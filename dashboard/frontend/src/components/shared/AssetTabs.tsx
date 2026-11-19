import { ASSET_LABELS, type AssetTab } from './assetTabUtils'

export function AssetTabs({
  asset,
  allowedTabs,
  onChange,
}: {
  asset: AssetTab
  allowedTabs: readonly AssetTab[]
  onChange: (asset: AssetTab) => void
}) {
  return (
    <div
      role="tablist"
      style={{
        display: 'inline-flex', gap: 2, padding: 3,
        background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 12,
      }}
    >
      {allowedTabs.map(tab => {
        const active = asset === tab
        return (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab)}
            style={{
              border: 'none',
              background: active ? 'var(--seg-active)' : 'transparent',
              color: active ? 'var(--text)' : 'var(--text-2)',
              borderRadius: 9,
              height: 30,
              padding: '0 14px',
              fontSize: 14,
              fontWeight: active ? 600 : 500,
              cursor: 'pointer',
            }}
          >
            {ASSET_LABELS[tab]}
          </button>
        )
      })}
    </div>
  )
}
