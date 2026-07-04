import { Area, AreaChart, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { useApi } from '../../hooks/useApi'

interface DashboardData {
  coins?: Array<{
    symbol: string
    price: number | null
    change_24h: number | null
  }>
}

const horizons = [
  { label: '7일', direction: '상승', confidence: 68, tone: 'up' },
  { label: '14일', direction: '상승', confidence: 63, tone: 'up' },
  { label: '30일', direction: '중립', confidence: 55, tone: 'flat' },
  { label: '60일', direction: '하락', confidence: 48, tone: 'down' },
] as const

const metricCards = [
  { title: '방향 적중률', value: '67.3%', sub: '(최근 30일)', tone: 'up' },
  { title: '평균 수익률', value: '+8.45%', sub: '(최근 30일)', tone: 'up' },
  { title: '최대 연속 적중', value: '8회', sub: '(최근 30일)', tone: 'neutral' },
  { title: '총 예측 횟수', value: '256회', sub: '(최근 90일)', tone: 'neutral' },
] as const

const trendData = [
  { day: '03/01', spf: 62, btc: 68 },
  { day: '03/08', spf: 58, btc: 74 },
  { day: '03/16', spf: 52, btc: 79 },
  { day: '03/24', spf: 48, btc: 72 },
  { day: '03/31', spf: 45, btc: 66 },
  { day: '04/08', spf: 54, btc: 70 },
  { day: '04/15', spf: 61, btc: 74 },
  { day: '04/23', spf: 70, btc: 80 },
  { day: '04/30', spf: 64, btc: 82 },
  { day: '05/08', spf: 59, btc: 92 },
  { day: '05/15', spf: 66, btc: 104 },
  { day: '05/23', spf: 72, btc: 110 },
  { day: '05/30', spf: 82, btc: 102 },
  { day: '06/07', spf: 76, btc: 98 },
  { day: '06/14', spf: 72, btc: 96 },
]

const miniTrend = [
  { x: 1, y: 20 },
  { x: 2, y: 24 },
  { x: 3, y: 42 },
  { x: 4, y: 39 },
  { x: 5, y: 48 },
  { x: 6, y: 45 },
  { x: 7, y: 52 },
  { x: 8, y: 50 },
  { x: 9, y: 57 },
]

const records = [
  ['2025-06-14 09:00', '7일', '상승', '-', '판정 대기', '-'],
  ['2025-06-14 09:00', '14일', '상승', '-', '판정 대기', '-'],
  ['2025-06-14 09:00', '30일', '중립', '-', '판정 대기', '-'],
  ['2025-06-14 09:00', '60일', '하락', '-', '판정 대기', '-'],
  ['2025-06-07 09:00', '7일', '상승', '상승', '적중', '+3.21%'],
  ['2025-06-07 09:00', '14일', '상승', '상승', '적중', '+5.48%'],
  ['2025-06-07 09:00', '30일', '중립', '중립', '적중', '+1.02%'],
  ['2025-06-07 09:00', '60일', '하락', '중립', '불일치', '-1.14%'],
]

const leaderboard = [
  ['👑', '고래의꿈', '+27.41%', '71.3%', '58'],
  ['♛', '알트마스터', '+22.18%', '68.2%', '64'],
  ['👑', '차트헌터', '+18.92%', '65.4%', '51'],
  ['-', '나의 순위', '+18.62%', '62.5%', '48'],
]

function MiniSpark({ tone = 'up' }: { tone?: 'up' | 'down' | 'neutral' }) {
  const color = tone === 'down' ? '#ef4444' : tone === 'neutral' ? '#2d8cff' : '#36c273'

  return (
    <div className="mock-mini-spark">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={miniTrend} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`mini-${tone}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.35} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="x" hide />
          <YAxis hide domain={['dataMin - 4', 'dataMax + 4']} />
          <Area dataKey="y" stroke={color} strokeWidth={2} fill={`url(#mini-${tone})`} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function DirectionBadge({ value }: { value: string }) {
  const tone = value === '상승' ? 'up' : value === '하락' ? 'down' : 'flat'
  const icon = value === '상승' ? '↑' : value === '하락' ? '↓' : '−'

  return (
    <span className={`mock-direction mock-direction-${tone}`}>
      <i>{icon}</i>
      {value}
    </span>
  )
}

function Gauge() {
  return (
    <div className="mock-gauge" aria-label="SPF 점수 72점">
      <div className="mock-gauge-arc" />
      <div className="mock-gauge-needle" />
      <div className="mock-gauge-min">0</div>
      <div className="mock-gauge-max">100</div>
      <div className="mock-gauge-score">
        <b>72</b>
        <span>/100</span>
      </div>
    </div>
  )
}

export function Dashboard() {
  const { data } = useApi<DashboardData>('/api/dashboard', 60_000)
  const btc = data?.coins?.find(coin => coin.symbol === 'BTC')
  const btcPrice = btc?.price ? btc.price.toLocaleString() : '103,512.6'

  return (
    <div className="mock-spf-dashboard">
      <section className="mock-section-title">
        <h1>시장 방향 전망 <span>?</span></h1>
      </section>

      <div className="mock-content-grid">
        <section className="mock-card mock-spf-hero">
          <div className="mock-spf-copy">
            <h2>SPF</h2>
            <p>종합 방향</p>
            <DirectionBadge value="상승" />
            <dl>
              <div><dt>신뢰도</dt><dd>72%</dd></div>
              <div><dt>시장 상태</dt><dd>강세</dd></div>
              <div><dt>BTC 기준가</dt><dd>{btcPrice}</dd></div>
            </dl>
          </div>
          <Gauge />
        </section>

        <section className="mock-horizon-grid">
          {horizons.map(item => (
            <article className="mock-card mock-horizon-card" key={item.label}>
              <h3>{item.label}</h3>
              <DirectionBadge value={item.direction} />
              <div className="mock-divider" />
              <p>신뢰도 <b>{item.confidence}%</b></p>
              <p>판정 대기</p>
            </article>
          ))}
        </section>

        <section className="mock-card mock-trend-card">
          <div className="mock-card-head">
            <h2>SPF 추이</h2>
            <button type="button">90일⌄</button>
          </div>
          <div className="mock-chart-legend">
            <span><i className="mock-dot-blue" />SPF 점수</span>
            <span><i className="mock-dot-gray" />BTC 가격</span>
          </div>
          <div className="mock-main-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData} margin={{ top: 14, right: 18, bottom: 8, left: 0 }}>
                <XAxis dataKey="day" stroke="#8a96a8" tickLine={false} axisLine={false} />
                <YAxis yAxisId="left" stroke="#8a96a8" tickLine={false} axisLine={false} domain={[0, 100]} />
                <YAxis yAxisId="right" orientation="right" stroke="#8a96a8" tickLine={false} axisLine={false} domain={[40, 120]} />
                <Line yAxisId="left" dataKey="spf" stroke="#2d8cff" strokeWidth={2} dot={false} />
                <Line yAxisId="right" dataKey="btc" stroke="#8f98a8" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mock-chart-note">SPF(Sentiment & Price Flow) 점수는 시장 심리와 자금 흐름을 종합하여 산출합니다.</p>
        </section>

        <section className="mock-metric-grid">
          {metricCards.map(card => (
            <article className="mock-card mock-metric-card" key={card.title}>
              <h3>{card.title} <span>?</span></h3>
              <strong className={`mock-value-${card.tone}`}>{card.value}</strong>
              <small>{card.sub}</small>
              <MiniSpark tone={card.tone === 'up' ? 'up' : card.tone === 'neutral' ? 'neutral' : 'down'} />
            </article>
          ))}
        </section>

        <section className="mock-card mock-record-card">
          <div className="mock-card-head">
            <h2>최근 예측 기록</h2>
            <button type="button">전체 보기</button>
          </div>
          <div className="mock-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>예측 일시</th>
                  <th>기간</th>
                  <th>예측 방향</th>
                  <th>실제 방향</th>
                  <th>적중 여부</th>
                  <th>수익률</th>
                </tr>
              </thead>
              <tbody>
                {records.map(row => (
                  <tr key={`${row[0]}-${row[1]}-${row[4]}`}>
                    {row.map((cell, index) => (
                      <td key={index} className={cell.includes('+') ? 'mock-up' : cell.includes('-1') || cell === '불일치' ? 'mock-down' : ''}>
                        {index === 2 || index === 3 ? <DirectionBadge value={cell} /> : cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mock-card mock-simulator-card">
          <div className="mock-card-head">
            <h2>시뮬레이터 <span>?</span></h2>
            <button type="button" className="mock-primary-button">▶ 시뮬레이터 실행</button>
          </div>
          <div className="mock-sim-grid">
            <div><span>누적 수익률</span><b>+18.62%</b><MiniSpark /></div>
            <div><span>벤치마크 (BTC)</span><b>+9.37%</b><MiniSpark tone="neutral" /></div>
            <div><span>초과 수익률</span><b>+9.25%</b><MiniSpark /></div>
            <div><span>승률</span><strong>62.5%</strong><small>(30일)</small></div>
            <div><span>거래 횟수</span><strong>48회</strong><small>(30일)</small><em>최대 낙폭 -6.42%</em></div>
          </div>
        </section>

        <section className="mock-card mock-leaderboard-card">
          <div className="mock-card-head">
            <h2>리더보드</h2>
            <button type="button">전체 보기</button>
          </div>
          <div className="mock-tabs">
            <button type="button" className="mock-tab-active">종합 수익률</button>
            <button type="button">적중률</button>
            <button type="button">연승</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>순위</th>
                <th>사용자</th>
                <th>수익률</th>
                <th>적중률</th>
                <th>거래 횟수</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map(row => (
                <tr key={row[1]} className={row[1] === '나의 순위' ? 'mock-my-rank' : ''}>
                  {row.map((cell, index) => (
                    <td key={index} className={index === 2 ? 'mock-up' : ''}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  )
}
