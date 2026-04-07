import { useState, useEffect, useCallback } from 'react'
import { useApi } from '../../hooks/useApi'

interface Post {
  id: number
  badge: string
  title: string
  subtitle: string
  category: string
  views: number
  read_time: number
  published_at: string
  content?: string
}

interface PostList {
  posts: Post[]
  total: number
}

const CATEGORY_COLORS: Record<string, string> = {
  '매크로': '#60a5fa',
  '온체인': '#4ade80',
  '파생상품': '#f97316',
  '알트코인': '#a78bfa',
  '기술적분석': '#f59e0b',
  '시장분석': '#f87171',
  '기타': '#94a3b8',
}

function categoryColor(cat: string): string {
  return CATEGORY_COLORS[cat] ?? '#94a3b8'
}

function PostCard({ post, onClick }: { post: Post; onClick: () => void }) {
  const catColor = categoryColor(post.category)
  const date = post.published_at?.slice(0, 10)

  return (
    <div
      onClick={onClick}
      onContextMenu={e => e.preventDefault()}
      style={{
        background: '#111827',
        border: '1px solid #1e293b',
        borderRadius: 12,
        padding: '18px 20px',
        cursor: 'pointer',
        transition: 'border-color 0.15s, transform 0.1s',
        userSelect: 'none',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = '#334155'
        ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = '#1e293b'
        ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)'
      }}
    >
      {/* 상단: 배지 + 카테고리 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        {post.badge && (
          <span style={{
            padding: '2px 9px', borderRadius: 6, fontSize: '0.7rem', fontWeight: 700,
            background: 'rgba(245,158,11,0.15)', color: '#f59e0b',
          }}>
            {post.badge}
          </span>
        )}
        {post.category && (
          <span style={{
            padding: '2px 9px', borderRadius: 6, fontSize: '0.7rem',
            background: `${catColor}20`, color: catColor,
          }}>
            {post.category}
          </span>
        )}
      </div>

      {/* 제목 */}
      <div style={{ color: '#e2e8f0', fontWeight: 600, fontSize: '0.95rem', marginBottom: 6, lineHeight: 1.4 }}>
        {post.title}
      </div>

      {/* 부제목 */}
      {post.subtitle && (
        <div style={{ color: '#64748b', fontSize: '0.8rem', marginBottom: 12, lineHeight: 1.5 }}>
          {post.subtitle}
        </div>
      )}

      {/* 하단: 날짜 + 조회수 + 읽기 시간 */}
      <div style={{ display: 'flex', gap: 12, color: '#64748b', fontSize: '0.72rem' }}>
        <span>{date}</span>
        <span>👁 {post.views}</span>
        <span>⏱ {post.read_time}분</span>
      </div>
    </div>
  )
}

function PostModal({ postId, onClose }: { postId: number; onClose: () => void }) {
  const [post, setPost] = useState<Post | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`/api/research/${postId}`)
      .then(r => r.json())
      .then(data => { setPost(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [postId])

  // ESC 키로 닫기
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: '40px 16px', overflowY: 'auto',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{
          background: '#111827',
          border: '1px solid #1e293b',
          borderRadius: 16,
          width: '100%', maxWidth: 760,
          padding: '32px',
          position: 'relative',
        }}
        onContextMenu={e => e.preventDefault()}
      >
        {/* 닫기 버튼 */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 16, right: 16,
            background: '#1e293b', border: 'none', borderRadius: 8,
            color: '#94a3b8', fontSize: '1.1rem', width: 36, height: 36,
            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          ✕
        </button>

        {loading && (
          <div style={{ color: '#64748b', textAlign: 'center', padding: '48px 0' }}>
            로드 중...
          </div>
        )}

        {!loading && post && (
          <>
            {/* 배지 + 카테고리 */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              {post.badge && (
                <span style={{
                  padding: '3px 12px', borderRadius: 8, fontSize: '0.75rem', fontWeight: 700,
                  background: 'rgba(245,158,11,0.15)', color: '#f59e0b',
                }}>
                  {post.badge}
                </span>
              )}
              {post.category && (
                <span style={{
                  padding: '3px 12px', borderRadius: 8, fontSize: '0.75rem',
                  background: `${categoryColor(post.category)}20`,
                  color: categoryColor(post.category),
                }}>
                  {post.category}
                </span>
              )}
            </div>

            {/* 제목 */}
            <h2 style={{ color: '#f1f5f9', fontSize: '1.3rem', fontWeight: 700, marginBottom: 8, lineHeight: 1.4 }}>
              {post.title}
            </h2>

            {/* 부제목 */}
            {post.subtitle && (
              <p style={{ color: '#64748b', fontSize: '0.88rem', marginBottom: 20, lineHeight: 1.6 }}>
                {post.subtitle}
              </p>
            )}

            {/* 메타 */}
            <div style={{ display: 'flex', gap: 16, color: '#64748b', fontSize: '0.75rem', marginBottom: 24, borderBottom: '1px solid #1e293b', paddingBottom: 16 }}>
              <span>{post.published_at?.slice(0, 10)}</span>
              <span>👁 {post.views}</span>
              <span>⏱ {post.read_time}분</span>
            </div>

            {/* 본문 */}
            <div
              style={{
                color: '#cbd5e1', fontSize: '0.9rem', lineHeight: 1.8,
                whiteSpace: 'pre-wrap', userSelect: 'none',
              }}
            >
              {post.content}
            </div>
          </>
        )}

        {!loading && !post && (
          <div style={{ color: '#64748b', textAlign: 'center', padding: '48px 0' }}>
            글을 불러올 수 없습니다
          </div>
        )}
      </div>
    </div>
  )
}

const CATEGORIES = ['전체', '매크로', '온체인', '파생상품', '알트코인', '기술적분석', '시장분석', '기타']

export function Research() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [category, setCategory] = useState('전체')

  const { data, loading } = useApi<PostList>('/api/research?limit=50', 60_000)

  const filtered = category === '전체'
    ? (data?.posts ?? [])
    : (data?.posts ?? []).filter(p => p.category === category)

  const handleOpen = useCallback((id: number) => {
    setSelectedId(id)
  }, [])

  const handleClose = useCallback(() => {
    setSelectedId(null)
  }, [])

  if (loading || !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* 스켈레톤 */}
        {[1, 2, 3].map(i => (
          <div key={i} style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12, padding: '18px 20px', height: 120 }}>
            <div style={{ background: '#1e293b', borderRadius: 4, height: 12, width: '30%', marginBottom: 12 }} />
            <div style={{ background: '#1e293b', borderRadius: 4, height: 16, width: '70%', marginBottom: 8 }} />
            <div style={{ background: '#1e293b', borderRadius: 4, height: 12, width: '90%' }} />
          </div>
        ))}
      </div>
    )
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* 카테고리 필터 */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              style={{
                padding: '5px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
                fontSize: '0.8rem',
                background: category === cat ? '#2563eb' : '#1e293b',
                color: category === cat ? '#fff' : '#94a3b8',
                transition: 'all 0.1s',
              }}
            >
              {cat}
            </button>
          ))}
          <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: '0.75rem', alignSelf: 'center' }}>
            {filtered.length}건
          </span>
        </div>

        {/* 글 그리드 */}
        {filtered.length > 0 ? (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: 12,
          }}>
            {filtered.map(post => (
              <PostCard key={post.id} post={post} onClick={() => handleOpen(post.id)} />
            ))}
          </div>
        ) : (
          <div style={{
            textAlign: 'center', padding: '64px 0',
            color: '#64748b', fontSize: '0.9rem',
          }}>
            {category === '전체'
              ? '리서치 글이 없습니다'
              : `${category} 카테고리 글이 없습니다`}
          </div>
        )}

      </div>

      {/* 모달 */}
      {selectedId != null && (
        <PostModal postId={selectedId} onClose={handleClose} />
      )}
    </>
  )
}
