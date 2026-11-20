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
      <h2 className="dash-card-title dash-news-head">주요 경제 뉴스</h2>
      <div className="v2-list">
        {data.map((item, idx) => (
          <a
            key={idx}
            className="dash-news-item"
            href={/^https?:\/\//i.test(item.link) ? item.link : '#'}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span className="dash-news-title">{item.title}</span>
            <span className="dash-news-meta">
              {item.source}{item.pub_date ? ` ${item.pub_date.slice(5, 16).replace('T', ' ')}` : ''}
            </span>
          </a>
        ))}
      </div>
    </Card>
  )
}
