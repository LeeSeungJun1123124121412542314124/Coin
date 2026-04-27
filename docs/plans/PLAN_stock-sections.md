# 대시보드 — 한국주식 / 미국주식 섹션 추가

## 요구사항 요약
- 코인 카드 섹션 아래: 한국주식 섹션
- 그 아래: 미국주식 섹션
- UI: StockIndexCard 스타일 (가격+변동률+스파크라인+H/L)
- 클릭: TradingView 차트 모달 (코인과 동일)
- 편집: 슬롯 편집 가능 (코인 슬롯과 동일 패턴)
- 데이터: Yahoo Finance (기존 인프라 재사용)

## 기본 종목
| 시장 | 종목 | Yahoo 티커 | TradingView 심볼 |
|------|------|-----------|----------------|
| 한국 | 삼성전자 | 005930.KS | KRX:005930 |
| 한국 | SK하이닉스 | 000660.KS | KRX:000660 |
| 한국 | 카카오 | 035720.KS | KRX:035720 |
| 한국 | 현대차 | 005380.KS | KRX:005380 |
| 한국 | NAVER | 035420.KS | KRX:035420 |
| 미국 | Apple | AAPL | NASDAQ:AAPL |
| 미국 | Microsoft | MSFT | NASDAQ:MSFT |
| 미국 | NVIDIA | NVDA | NASDAQ:NVDA |
| 미국 | Tesla | TSLA | NASDAQ:TSLA |
| 미국 | Alphabet | GOOGL | NASDAQ:GOOGL |

---

## Phase 1 — DB 스키마: stock_slots 테이블

`dashboard/backend/db/schema.sql`에 추가:

```sql
CREATE TABLE IF NOT EXISTS stock_slots (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    market   TEXT NOT NULL,          -- 'kr' | 'us'
    position INTEGER NOT NULL,
    ticker   TEXT NOT NULL,          -- Yahoo Finance 티커
    name     TEXT NOT NULL,          -- 표시명
    tv_symbol TEXT,                  -- TradingView 심볼
    UNIQUE(market, position)
);
```

`dashboard/backend/db/connection.py`의 `_init_schema()`에서 자동 생성 + 기본 종목 INSERT(OR IGNORE):
```python
conn.executemany(
    "INSERT OR IGNORE INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES (?,?,?,?,?)",
    [
        ('kr', 1, '005930.KS', '삼성전자', 'KRX:005930'),
        ('kr', 2, '000660.KS', 'SK하이닉스', 'KRX:000660'),
        ('kr', 3, '035720.KS', '카카오', 'KRX:035720'),
        ('kr', 4, '005380.KS', '현대차', 'KRX:005380'),
        ('kr', 5, '035420.KS', 'NAVER', 'KRX:035420'),
        ('us', 1, 'AAPL', 'Apple', 'NASDAQ:AAPL'),
        ('us', 2, 'MSFT', 'Microsoft', 'NASDAQ:MSFT'),
        ('us', 3, 'NVDA', 'NVIDIA', 'NASDAQ:NVDA'),
        ('us', 4, 'TSLA', 'Tesla', 'NASDAQ:TSLA'),
        ('us', 5, 'GOOGL', 'Alphabet', 'NASDAQ:GOOGL'),
    ]
)
```

---

## Phase 2 — Backend: fetch_stock_prices()

`dashboard/backend/collectors/yahoo_finance.py`에 신규 함수 추가:

```python
@cached(ttl=300, key_prefix="stock_prices")
async def fetch_stock_prices(tickers: tuple[str, ...]) -> list[dict]:
    """개별 주식 현재가 + 스파크라인 (5분 캐시)."""
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        results = await asyncio.gather(*[_fetch_single_yahoo_stock(client, t) for t in tickers])
    return [r for r in results if r is not None]
```

`_fetch_single_yahoo_stock`: 기존 `_fetch_single_yahoo`와 동일 로직, 단 `_TICKERS` 딕셔너리 대신 ticker 문자열 직접 사용. name은 호출자가 전달.

---

## Phase 3 — Backend: stock_slots_routes.py (신규)

`dashboard/backend/api/stock_slots_routes.py`:

```
GET  /api/stock-slots/{market}          → 슬롯 목록 [{position, ticker, name, tv_symbol}]
PUT  /api/stock-slots/{market}/{position} → 슬롯 업데이트 {ticker, name, tv_symbol}
GET  /api/stock-prices/{market}         → 현재가 [{ticker, name, tv_symbol, price, change_pct, sparkline, high, low}]
```

- `main.py` `_mount_dashboard_routers()`에 라우터 등록

---

## Phase 4 — Frontend: StockCard 컴포넌트 (신규)

`dashboard/frontend/src/components/shared/StockCard.tsx`:

- `StockIndexCard`와 동일한 UI
- Props에 `tv_symbol` 추가
- `onOpenModal(tv_symbol, name)` 콜백 → TradingView 모달 오픈
- 기존 StockIndexCard와 분리 (지수 카드는 StockIndexModal, 종목 카드는 TradingView)

---

## Phase 5 — Frontend: StockSlotEditor 컴포넌트 (신규)

`dashboard/frontend/src/components/shared/StockSlotEditor.tsx`:

- `CoinSlotEditor` 패턴 참조
- Props: `{ market: 'kr' | 'us', slots, onUpdate }`
- 각 슬롯: ticker 입력 + name 입력 + tv_symbol 입력
- `PUT /api/stock-slots/{market}/{position}` 호출

---

## Phase 6 — Frontend: Dashboard.tsx 통합

```tsx
{/* ── 한국주식 ── */}
<section>
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
    <h2>한국주식</h2>
    <button onClick={() => setEditingKr(!editingKr)}>편집</button>
  </div>
  {editingKr && <StockSlotEditor market="kr" ... />}
  <div className="grid-coins">
    {krStocks?.map(s => <StockCard key={s.ticker} ... onOpenModal={openTvModal} />)}
  </div>
</section>

{/* ── 미국주식 ── */}
<section>
  ...동일 패턴...
</section>

{/* TradingView 모달 — 종목용 (기존 코인 모달 재사용) */}
{activeTvStock && (
  <Modal ...>
    <TradingViewChart symbol={activeTvStock.tv_symbol} />
  </Modal>
)}
```

상태:
```tsx
const [krStocks] = useApi('/api/stock-prices/kr', 300_000)
const [usStocks] = useApi('/api/stock-prices/us', 300_000)
const [activeTvStock, setActiveTvStock] = useState<{tv_symbol: string, name: string} | null>(null)
const [editingKr, setEditingKr] = useState(false)
const [editingUs, setEditingUs] = useState(false)
```

---

## 변경 대상 파일 요약

| 파일 | 유형 | 핵심 |
|------|------|------|
| `dashboard/backend/db/schema.sql` | 수정 | stock_slots 테이블 + 기본 데이터 |
| `dashboard/backend/db/connection.py` | 수정 | stock_slots 초기화 |
| `dashboard/backend/collectors/yahoo_finance.py` | 수정 | `fetch_stock_prices()` 신규 |
| `dashboard/backend/api/stock_slots_routes.py` | 신규 | 슬롯 CRUD + 현재가 API |
| `dashboard/backend/main.py` | 수정 | 라우터 등록 |
| `dashboard/frontend/src/components/shared/StockCard.tsx` | 신규 | 종목 카드 |
| `dashboard/frontend/src/components/shared/StockSlotEditor.tsx` | 신규 | 슬롯 편집 UI |
| `dashboard/frontend/src/components/screens/Dashboard.tsx` | 수정 | 두 섹션 추가 |

---

## Verification

```bash
# 1. API 확인
curl /api/stock-slots/kr | jq '.'       # 슬롯 목록
curl /api/stock-prices/kr | jq '.[].name'  # 삼성전자 등 5개
curl /api/stock-prices/us | jq '.[].name'  # AAPL 등 5개

# 2. 빌드
cd dashboard/frontend && npm run build  # TS 에러 없음

# 3. 브라우저
# - 코인 섹션 아래 한국주식 5장
# - 그 아래 미국주식 5장
# - 카드 클릭 → TradingView 모달
# - 편집 버튼 → 슬롯 편집
```

## Out of Scope
- 52주 고가/저가
- 재무 데이터 (PER, PBR 등)
- 종목 검색 자동완성
- 정렬/필터
