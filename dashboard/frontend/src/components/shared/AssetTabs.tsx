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
    <div style={{ display: 'flex', gap: 8 }}>
      {allowedTabs.map(tab => {
        const active = asset === tab
        return (
          <button
            key={tab}
            type="button"
            onClick={() => onChange(tab)}
            style={{
              border: `1px solid ${active ? '#38bdf8' : '#334155'}`,
              background: active ? 'rgba(56,189,248,0.12)' : '#0f172a',
              color: active ? '#e0f2fe' : '#94a3b8',
              borderRadius: 8,
              padding: '8px 12px',
              fontSize: '0.82rem',
              fontWeight: 700,
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
