# 대시보드 — 글로벌 지수 카드 + 경제뉴스 섹션

## Seed YAML

```yaml
goal: Dashboard Hero에 NASDAQ/KOSPI/KOSDAQ 지수 카드 3장 및 경제뉴스 RSS 섹션 추가

constraints:
  - 기존 yahoo_finance.py 컬렉터 확장 (신규 의존성 최소화)
  - RSS 파싱: feedparser 또는 httpx + xml.etree 사용
  - FastAPI / React / Recharts 스택 유지
  - "@cached / useApi / Card 컴포넌트 재사용"
  - 신규 패키지 설치 전 사용자 승인 필수

acceptance_criteria:
  - Dashboard Hero에 NASDAQ·KOSPI·KOSDAQ 카드 3장 표시
  - 각 카드: 현재가 + 변동률(당일) + 미니 스파크라인(5일)
  - 카드 클릭 → 모달 → 30일 라인차트
  - Hero 아래 경제뉴스 섹션 (연합뉴스 / Google News / 한국경제 RSS)
  - 뉴스 6개, 제목+링크만 표시, 15분 갱신
  - KOSDAQ(^KQ11) 신규 티커 수집
  - "npm run build" TypeScript 에러 없음

ontology_schema:
  name: GlobalMarketIndices
  description: 글로벌 주식 지수 현황·히스토리 및 경제 뉴스 피드
  fields:
    - name: ticker
      type: string
      description: Yahoo Finance 심볼 (^IXIC, ^KS11, ^KQ11)
    - name: name
      type: string
      description: 지수 표시명
    - name: price
      type: number
      description: 현재가
    - name: change_pct
      type: number
      description: 당일 변동률 (%)
    - name: sparkline
      type: array
      description: 최근 5일 종가 배열
    - name: history
      type: array
      description: "30일 [{date, close}] 배열 — 모달 차트용"
    - name: news_title
      type: string
      description: 뉴스 제목
    - name: news_link
      type: string
      description: 뉴스 원문 URL
    - name: news_pub_date
      type: string
      description: 발행 시각 (ISO 8601)
    - name: news_source
      type: string
      description: 출처 (연합뉴스 / 한국경제 / Google News)

evaluation_principles:
  - name: ui_consistency
    description: 기존 Card / GlobalMarketCard 스타일 준수
    weight: 0.35
  - name: api_resilience
    description: Yahoo Finance 실패 시 graceful degradation (null 반환)
    weight: 0.30
  - name: performance
    description: "RSS 15분 캐시, 차트 히스토리 1시간 캐시"
    weight: 0.20
  - name: type_safety
    description: TypeScript 엄격 타입, import type 규칙 준수
    weight: 0.15

exit_conditions:
  - name: build_pass
    description: npm run build TypeScript 에러 없음
    criteria: 빌드 성공
  - name: data_visible
    description: 브라우저에서 3개 지수 카드 및 뉴스 6개 정상 표시
    criteria: UI 시각 검증
  - name: modal_works
    description: 카드 클릭 시 30일 차트 모달 팝업
    criteria: 모달 동작 확인

metadata:
  ambiguity_score: 0.12
  version: "1.0"
  created: "2026-04-18"
  project_type: brownfield
```

---

## 컨텍스트 참조

| 파일 | 역할 |
|------|------|
| `dashboard/backend/collectors/yahoo_finance.py` | NASDAQ·KOSPI 현재가 수집 기존 구현 — 확장 대상 |
| `dashboard/backend/api/dashboard_routes.py` | Hero 데이터 통합 엔드포인트 — 신규 필드 추가 |
| `dashboard/frontend/src/components/screens/Dashboard.tsx` | Hero 카드 레이아웃 — 카드 3장 + 뉴스 섹션 추가 |
| `dashboard/frontend/src/components/shared/GlobalMarketCard.tsx` | Hero 카드 컴포넌트 패턴 참조 |
| `dashboard/frontend/src/components/shared/CoinChartModal.tsx` | 클릭 시 차트 모달 패턴 참조 |

---

## 구현 계획

### Phase 1 — Backend: yahoo_finance.py 확장

**1-1. KOSDAQ 티커 추가**

`_TICKERS` 딕셔너리에 `"^KQ11": {"name": "KOSDAQ", "category": "korea"}` 추가.

**1-2. `fetch_index_history(ticker, days=30)` 신규 함수**

Yahoo Finance v8 API `?interval=1d&range=30d`로 30일 종가 히스토리 반환.
`@cached(ttl=3600)` 적용. 실패 시 `None` 반환(graceful degradation).

```python
@cached(ttl=3600, key_prefix="yahoo_history")
async def fetch_index_history(ticker: str, days: int = 30) -> list[dict] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"interval": "1d", "range": f"{days}d"})
            resp.raise_for_status()
            result = resp.json()["chart"]["result"][0]
            timestamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
            return [
                {"date": datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), "close": round(c, 2)}
                for t, c in zip(timestamps, closes)
                if c is not None
            ]
    except Exception as e:
        logger.warning("지수 히스토리 조회 실패 (%s): %s", ticker, e)
        return None
```

### Phase 2 — Backend: 뉴스 컬렉터 신규

**신규** `dashboard/backend/collectors/economic_news.py`:

RSS 피드 3종 파싱, `@cached(ttl=900)` 적용.

```python
_RSS_FEEDS = [
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("한국경제", "https://www.hankyung.com/feed/economy"),
    ("Google News", "https://news.google.com/rss/search?q=경제&hl=ko&gl=KR&ceid=KR:ko"),
]

@cached(ttl=900, key_prefix="economic_news")
async def fetch_economic_news(limit: int = 6) -> list[dict]:
    """RSS 3종 파싱 후 최신순 정렬, limit개 반환."""
    ...
```

각 항목: `{"title", "link", "pub_date", "source"}`

### Phase 3 — Backend: dashboard_routes.py 확장

`asyncio.gather`에 지수 히스토리 3종 + 뉴스 추가:

```python
nasdaq_hist, kospi_hist, kosdaq_hist, econ_news = await asyncio.gather(
    fetch_index_history("^IXIC"),
    fetch_index_history("^KS11"),
    fetch_index_history("^KQ11"),
    fetch_economic_news(),
    return_exceptions=True,
)
```

응답 JSON에 `stock_indices`(현재가+히스토리), `economic_news` 키 추가.

### Phase 4 — Backend: stock_index API 엔드포인트 (선택)

dashboard_routes에 통합하거나 `/api/stock-indices` 별도 라우트 추가.
히스토리 데이터 크기를 고려해 별도 엔드포인트가 적합:

- `GET /api/stock-indices` → 현재가 + 스파크라인 (Hero 카드용, 5분 캐시)
- `GET /api/stock-index-history/{ticker}` → 30일 히스토리 (모달용, 1시간 캐시)

### Phase 5 — Frontend: StockIndexCard 컴포넌트 신규

**신규** `dashboard/frontend/src/components/shared/StockIndexCard.tsx`:

- Props: `{ name, price, change_pct, sparkline, ticker }`
- 구조: 지수명 배지 → 현재가 + 변동률 → 미니 스파크라인(Recharts AreaChart, 높이 40px)
- 클릭 → `onOpenModal(ticker)` 콜백 호출
- 상승 녹색(#4ade80) / 하락 빨강(#f87171) 동적 색상

### Phase 6 — Frontend: StockIndexModal 컴포넌트 신규

**신규** `dashboard/frontend/src/components/shared/StockIndexModal.tsx`:

- CoinChartModal 패턴 참조
- Props: `{ ticker, name, onClose }`
- 내부: `useApi('/api/stock-index-history/{ticker}', 3_600_000)` 로 히스토리 fetch
- Recharts LineChart 30일 라인차트 표시

### Phase 7 — Frontend: EconomicNewsSection 컴포넌트 신규

**신규** `dashboard/frontend/src/components/shared/EconomicNewsSection.tsx`:

- `useApi('/api/economic-news', 900_000)` (15분 갱신)
- 뉴스 6개 리스트: `<a href={link} target="_blank">제목</a>` + 출처·시간
- Card 래퍼

### Phase 8 — Frontend: Dashboard.tsx 통합

1. `useApi('/api/stock-indices', 300_000)` 추가
2. Hero 그리드에 StockIndexCard 3장 추가 (NASDAQ·KOSPI·KOSDAQ)
3. 모달 상태 관리: `const [activeIndex, setActiveIndex] = useState<string|null>(null)`
4. Hero 아래 EconomicNewsSection 삽입
5. StockIndexModal 조건부 렌더

---

## 변경 대상 파일 요약

| 파일 | 유형 | 핵심 |
|------|------|------|
| `dashboard/backend/collectors/yahoo_finance.py` | 수정 | KOSDAQ 티커 추가, `fetch_index_history()` 신규 |
| `dashboard/backend/collectors/economic_news.py` | 신규 | RSS 3종 파싱, `fetch_economic_news()` |
| `dashboard/backend/api/dashboard_routes.py` | 수정 | 지수 히스토리+뉴스 gather 추가, 응답 확장 |
| `dashboard/backend/api/market_routes.py` (또는 신규) | 수정/신규 | `/api/stock-indices`, `/api/stock-index-history/{ticker}`, `/api/economic-news` |
| `dashboard/frontend/src/components/shared/StockIndexCard.tsx` | 신규 | 지수 Hero 카드 |
| `dashboard/frontend/src/components/shared/StockIndexModal.tsx` | 신규 | 30일 차트 모달 |
| `dashboard/frontend/src/components/shared/EconomicNewsSection.tsx` | 신규 | RSS 뉴스 리스트 |
| `dashboard/frontend/src/components/screens/Dashboard.tsx` | 수정 | 카드 3장 + 뉴스 섹션 추가 |

---

## Verification

```bash
# 1. 백엔드 API 확인
curl http://localhost:8000/api/stock-indices -H "Authorization: Bearer <token>" | jq '.'
# → NASDAQ/KOSPI/KOSDAQ price, change_pct, sparkline 확인

curl http://localhost:8000/api/stock-index-history/%5EIXIC -H "Authorization: Bearer <token>" | jq '.history | length'
# → 약 30 (영업일 기준)

curl http://localhost:8000/api/economic-news -H "Authorization: Bearer <token>" | jq '.[].title'
# → 6개 뉴스 제목 출력

# 2. 프론트 빌드
cd dashboard/frontend && npm run build
# → TypeScript 에러 없음

# 3. 브라우저 시각 확인
# - Hero에 NASDAQ/KOSPI/KOSDAQ 카드 3장 표시
# - 각 카드 클릭 → 30일 라인차트 모달
# - Hero 아래 뉴스 6개 (제목+링크)
```

## Out of Scope
- 캔들차트 (1차 구현은 라인차트, 추후 확장 가능)
- 뉴스 AI 요약
- 지수 알림/임계값 설정
- 해외 지수 (S&P500, 닛케이 등) 추가
- 차트 기간 선택 UI
