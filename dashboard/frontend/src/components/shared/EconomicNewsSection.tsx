import { useApi } from '../../hooks/useApi'
import { Card } from './Card'

interface NewsItem {
  title: string
  link: string
  pub_date: string
  source: string
}

export function EconomicNewsSection() {
  const { data, loading } = useApi<NewsItem[]>('/api/economic-news', 900_000)

  if (loading || !data || data.length === 0) return null

  return (
    <Card>
      <div style={{ color: 'var(--text-2)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 12 }}>
        주요 경제 뉴스
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.map((item, idx) => (
          <div key={idx} style={{ borderBottom: idx < data.length - 1 ? '1px solid var(--line)' : 'none', paddingBottom: idx < data.length - 1 ? 10 : 0 }}>
            <a
              href={/^https?:\/\//i.test(item.link) ? item.link : '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--text)', fontSize: '0.85rem', lineHeight: 1.4, textDecoration: 'none', display: 'block' }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--link-hover)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text)' }}
            >
              {item.title}
            </a>
            <div style={{ marginTop: 4, display: 'flex', gap: 8, fontSize: '0.7rem', color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
              <span>{item.source}</span>
              {item.pub_date && (
                <span>{item.pub_date.slice(0, 16).replace('T', ' ')}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
