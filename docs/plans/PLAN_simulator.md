# PLAN: 페이퍼 트레이딩 + 예측 검증 시뮬레이터

**Seed ID:** seed_a32c0844911a
**Interview ID:** interview_20260419_071619
**작성일:** 2026-04-19

## 목표

코인/한국주식/미국주식 3시장을 아우르는 페이퍼 트레이딩 + 예측 검증 시스템.
사용자가 포지션을 미리 등록 → 실제 시장 움직임으로 자동 채점 → 지표별 적중률을 수동 튜닝 라벨로 축적.

---

## 핵심 설계 결정

| 항목 | 결정 |
|---|---|
| 예측 모드 | 방향성 / 목표가 / 페이퍼 포트폴리오 (3가지 동시 지원) |
| 계좌 구조 | 시장별 3계좌 독립 (코인=USDT / 한국주식=KRW / 미국주식=USD) |
| 코인 판정 | 바이비트 1시간봉 고가/저가 기준 (청산·TP·SL 판정) |
| 주식 판정 | 일봉 종가 기준 |
| 선물 시뮬 | 바이비트 USDT-M 공식, 최대 64배, 펀딩비 8시간마다 FR 차감 |
| 수수료 | 무시 |
| 지표 태깅 | 수집 중인 지표 체크박스 (OI/FR/F&G/알트시즌/VIX/DXY/US10Y/금/은) |
| 스코어카드 | 지표별·시장별·기간별 적중률 누적 (수동 튜닝 라벨) |
| 초기 자본 | 사용자 입력, 리셋 허용 (히스토리 영구 보존) |

---

## DB 스키마

### sim_accounts
```sql
CREATE TABLE sim_accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    market     TEXT NOT NULL CHECK(market IN ('crypto','kr_stock','us_stock')),
    currency   TEXT NOT NULL,           -- USDT / KRW / USD
    capital    REAL NOT NULL,           -- 현재 잔액
    initial_capital REAL NOT NULL,
    reset_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### sim_predictions
```sql
CREATE TABLE sim_predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES sim_accounts(id),
    asset_symbol    TEXT NOT NULL,      -- "BTC/USDT", "005930.KS", "AAPL"
    mode            TEXT NOT NULL CHECK(mode IN ('direction','target_price','portfolio')),
    direction       TEXT CHECK(direction IN ('long','short')),
    target_price    REAL,
    entry_price     REAL NOT NULL,
    entry_time      TEXT NOT NULL,      -- ISO 8601
    expiry_time     TEXT NOT NULL,
    status          TEXT DEFAULT 'pending' CHECK(status IN ('pending','settled','liquidated','cancelled')),
    indicator_tags  TEXT,               -- JSON 배열: ["OI","FR","FnG"]
    note            TEXT,
    created_at      TEXT NOT NULL
);
```

### sim_positions
```sql
CREATE TABLE sim_positions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id       INTEGER NOT NULL REFERENCES sim_predictions(id),
    instrument_type     TEXT NOT NULL CHECK(instrument_type IN ('spot','futures')),
    quantity            REAL NOT NULL,
    leverage            INTEGER DEFAULT 1,
    stop_loss           REAL,
    take_profit         REAL,
    liquidation_price   REAL,          -- 바이비트 공식으로 계산
    funding_fee_accrued REAL DEFAULT 0
);
```

### sim_settlements
```sql
CREATE TABLE sim_settlements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id   INTEGER NOT NULL REFERENCES sim_predictions(id),
    settled_at      TEXT NOT NULL,
    actual_price    REAL NOT NULL,
    direction_hit   INTEGER,           -- 1/0/NULL
    price_error     REAL,              -- MAE
    pnl             REAL,
    pnl_pct         REAL,
    mdd             REAL,
    sharpe          REAL,
    liquidated      INTEGER DEFAULT 0
);
```

### sim_funding_events
```sql
CREATE TABLE sim_funding_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     INTEGER NOT NULL REFERENCES sim_positions(id),
    funding_time    TEXT NOT NULL,
    fr_value        REAL NOT NULL,
    funding_amount  REAL NOT NULL
);
```

### sim_account_resets (히스토리 보존)
```sql
CREATE TABLE sim_account_resets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES sim_accounts(id),
    reset_at    TEXT NOT NULL,
    capital_before REAL NOT NULL,
    new_capital    REAL NOT NULL
);
```

### coin_ohlcv_1h (코인 1시간봉)
```sql
CREATE TABLE coin_ohlcv_1h (
    symbol     TEXT NOT NULL,
    timestamp  INTEGER NOT NULL,       -- Unix ms
    open       REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, timestamp)
);
```

---

## Task 1: 바이비트 1시간봉 OHLCV 수집기

**파일:** `dashboard/backend/collectors/bybit_ohlcv.py` (신규)

```python
async def fetch_bybit_ohlcv_1h(symbol: str, limit: int = 200) -> list[dict]:
    """바이비트 1시간봉 OHLCV 조회 및 coin_ohlcv_1h 저장."""
```

**파일:** `dashboard/backend/jobs/collect_ohlcv.py` (신규)
- 매 정각 실행 (`0 * * * *`)
- BTC/USDT, ETH/USDT + 슬롯에 등록된 코인 심볼 동적 수집

**스케줄러 등록:** `dashboard/backend/main.py`에 `collect_ohlcv` 잡 추가

---

## Task 2: DB 마이그레이션

**파일:** `dashboard/backend/db/migrations/004_simulator.sql`

위 스키마 7개 테이블 생성. 기존 마이그레이션 시스템에 통합.

---

## Task 3: 선물 시뮬 엔진

**파일:** `dashboard/backend/services/sim_engine.py`

```python
def calc_liquidation_price(entry: float, leverage: int, direction: str) -> float:
    """바이비트 USDT-M 청산가 공식.
    
    롱: liq = entry * (1 - 1/leverage + MMR)
    숏: liq = entry * (1 + 1/leverage - MMR)
    바이비트 MMR: leverage별 테이블 적용
    """

def calc_funding_fee(quantity: float, entry_price: float, fr: float) -> float:
    """펀딩비 = 포지션 가치 * FR"""

async def apply_funding_fees(funding_time: str) -> None:
    """00/08/16 UTC에 활성 선물 포지션 전체 펀딩비 차감."""

async def check_sl_tp_liquidation(position_id: int) -> str | None:
    """최근 1시간봉 고가/저가로 SL/TP/청산 트리거 확인."""
```

**바이비트 MMR 테이블** (레버리지별 유지증거금률):
```python
_BYBIT_MMR = {
    1: 0.005, 2: 0.005, 3: 0.01, 5: 0.01,
    10: 0.02, 20: 0.025, 25: 0.025,
    50: 0.03, 64: 0.04,
}
```

---

## Task 4: 채점 스케줄러

**파일:** `dashboard/backend/jobs/settle_predictions.py`

- 매 시간 실행: `pending` 상태이고 `expiry_time <= now`인 예측 조회
- 코인: `coin_ohlcv_1h`에서 만료 시점 종가로 채점
- 주식: `fetch_naver_ohlcv` / `fetch_stock_ohlcv` 일봉 종가로 채점
- 방향 적중, MAE, PnL, MDD, 샤프 계산 후 `sim_settlements` 저장
- `sim_predictions.status = 'settled'` 업데이트

---

## Task 5: 시뮬레이터 API 라우터

**파일:** `dashboard/backend/api/sim_routes.py`

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/sim/accounts` | 3계좌 현황 조회 |
| POST | `/sim/accounts/{market}/reset` | 계좌 리셋 (히스토리 보존) |
| GET | `/sim/predictions` | 예측 목록 (필터: market/status/asset) |
| POST | `/sim/predictions` | 예측 등록 (3모드 공통) |
| DELETE | `/sim/predictions/{id}` | 예측 취소 (pending만 가능) |
| GET | `/sim/scorecard` | 스코어카드 집계 |
| GET | `/sim/scorecard/by-indicator` | 지표별 적중률 |
| GET | `/sim/positions/{id}` | 포지션 상세 (선물) |

---

## Task 6: 스코어카드 서비스

**파일:** `dashboard/backend/services/sim_scorecard.py`

```python
def get_scorecard(market: str | None, indicator: str | None, horizon_days: int | None) -> dict:
    """지표별·시장별·기간별 적중률, 평균 PnL, 샘플 수 집계."""
```

---

## Task 7: 프론트엔드 — 시뮬레이터 탭

**신규 화면:** `dashboard/frontend/src/components/screens/Simulator.tsx`

### 레이아웃
```
┌─────────────────────────────────────────────────────┐
│  💰 코인 (USDT)  |  🇰🇷 한국주식 (KRW)  |  🇺🇸 미국주식 (USD)  │ ← 계좌 탭
├─────────────────────────────────────────────────────┤
│  잔액: 10,000 USDT        수익률: +12.3%             │
│  [+ 새 예측 등록]  [계좌 리셋]                        │
├─────────────────────────────────────────────────────┤
│  활성 예측 목록                                       │
│  BTC/USDT  롱 x10  진입 83,000 → 현재 85,200  +2.6%  │
│  ...                                                 │
├─────────────────────────────────────────────────────┤
│  스코어카드                                           │
│  전체 적중률: 61%  (23/38건)                          │
│  [지표별 보기]  [기간별 보기]                          │
└─────────────────────────────────────────────────────┘
```

### 예측 등록 모달
- 모드 선택: 방향성 / 목표가 / 포트폴리오
- 자산 검색 (기존 `StockSlotEditor`의 search UI 재활용)
- 진입가 / 만료 시각 / 방향
- 포트폴리오 모드: 수량, 레버리지, SL, TP 추가 입력
- 지표 태깅: 체크박스 (OI, FR, F&G, 알트시즌, VIX, DXY, US10Y, 금, 은)
- 메모 (선택)

---

## Task 8: 프론트엔드 — 스코어카드 대시보드

**파일:** `dashboard/frontend/src/components/shared/SimScorecard.tsx`

- 지표별 적중률 바 차트 (Recharts)
- 시장별 PnL 히스토리 라인 차트
- 예측 히스토리 테이블 (만료/채점 결과 포함)

---

## Acceptance Criteria

- [ ] 방향성/목표가/포트폴리오 3모드 예측 등록
- [ ] 자유 기간 입력 (진입 + 만료 시각)
- [ ] 코인 선물 시뮬: 레버리지·청산가·펀딩비 계산 정확
- [ ] 한/미 주식 숏 방향 예측 등록
- [ ] 바이비트 1시간봉 수집 파이프라인 동작
- [ ] 만료 예측 자동 채점 스케줄러
- [ ] 지표 태깅 멀티 선택 UI
- [ ] 지표별·시장별 스코어카드
- [ ] 계좌 리셋 + 히스토리 보존
- [ ] 3계좌 독립 통화 표시
- [ ] 기존 대시보드 회귀 없음

---

## 구현 순서 (권장)

1. Task 2: DB 마이그레이션 (기반)
2. Task 1: 바이비트 1시간봉 수집기
3. Task 3: 선물 시뮬 엔진
4. Task 5: API 라우터
5. Task 4: 채점 스케줄러
6. Task 6: 스코어카드 서비스
7. Task 7: 프론트엔드 메인 화면
8. Task 8: 스코어카드 대시보드
