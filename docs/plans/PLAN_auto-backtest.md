# PLAN: 지표 자동 백테스트 (Auto Backtest)

**작성일:** 2026-04-19

## 목표

기술적 분석 지표 13개(RSI, MACD, 볼린저밴드, MA, EMA, 거래량, 지지/저항, 피보나치,
일목균형표, 스토캐스틱, 추세선, ADX, ATR)에 대해 과거 데이터 기반 자동 백테스트를 실행하여
"어떤 지표 신호가 얼마나 맞는지"를 수치로 보여준다.

---

## 핵심 설계 결정

| 항목 | 결정 |
|---|---|
| 데이터 소스 | 기존 `coin_ohlcv_1h` 테이블 (이미 수집 중) |
| 신호 방식 | 지표별 표준 규칙 → Long/Short 신호 |
| 판정 기준 | 신호 발생 후 N시간 뒤 종가로 방향 적중 판정 |
| 결과 캐시 | `auto_backtest_cache` 테이블 (TTL 1시간) |
| 조회 방식 | On-demand (API 요청 시 계산 후 캐시) |
| 지원 심볼 | coin_ohlcv_1h에 있는 코인 (BTC, ETH, SOL + 슬롯) |
| 수평선 | 4h / 8h / 24h (사용자 선택) |
| 롤백 기간 | 최근 500봉 (약 20일치 1시간봉) |

---

## 지표별 신호 규칙

| 지표 | 롱 신호 | 숏 신호 | 파라미터 |
|---|---|---|---|
| RSI | RSI < 30 (과매도) | RSI > 70 (과매수) | 14기간 |
| MACD | MACD선이 Signal선 상향돌파 | MACD선이 Signal선 하향돌파 | 12/26/9 |
| 볼린저밴드 | 종가가 하단밴드 하향 돌파 후 재진입 | 종가가 상단밴드 상향 돌파 후 재진입 | 20/2σ |
| MA | 종가가 MA 하향에서 상향 돌파 | 종가가 MA 상향에서 하향 돌파 | 20기간 |
| EMA | 종가가 EMA 하향에서 상향 돌파 | 종가가 EMA 상향에서 하향 돌파 | 20기간 |
| 거래량 | 거래량 > 20기간 평균 × 2 (급등봉) + 상승 | 거래량 > 20기간 평균 × 2 (급등봉) + 하락 | 20기간 |
| 지지/저항 | 지지선 근처(±0.5%) 반등 | 저항선 근처(±0.5%) 반락 | 20봉 최근 고저 |
| 피보나치 | 스윙 범위 61.8% 되돌림 + 반등 | 스윙 범위 61.8% 되돌림 + 반락 | 최근 50봉 고저 기준 |
| 일목균형표 | 종가가 구름대 위 + 전환선 > 기준선 | 종가가 구름대 아래 + 전환선 < 기준선 | 9/26/52 |
| 스토캐스틱 | %K < 20 이후 %D 상향돌파 | %K > 80 이후 %D 하향돌파 | 14/3/3 |
| 추세선 | 선형회귀 기울기 > 0 + 종가 > LR | 선형회귀 기울기 < 0 + 종가 < LR | 20기간 |
| ADX | ADX > 25 + +DI > -DI (추세 강도 롱) | ADX > 25 + -DI > +DI (추세 강도 숏) | 14기간 |
| ATR | (방향 판단 불가 — 변동성 지표) | ATR spike + 직전봉 방향으로 신호 | 14기간 |

---

## DB 스키마

### auto_backtest_cache

```sql
CREATE TABLE IF NOT EXISTS auto_backtest_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    horizon_h   INTEGER NOT NULL,    -- 판정 수평선 (4, 8, 24)
    lookback    INTEGER NOT NULL,    -- 분석에 사용한 봉 수
    computed_at TEXT NOT NULL,       -- ISO 8601
    result_json TEXT NOT NULL        -- JSON: 지표별 통계
);
CREATE INDEX IF NOT EXISTS idx_abt_cache ON auto_backtest_cache(symbol, horizon_h, computed_at);
```

---

## Task 목록

### Task 1: 기술적 지표 계산 엔진

**파일:** `dashboard/backend/services/ta_indicators.py` (신규)

```python
import numpy as np

def calc_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray: ...
def calc_macd(closes: np.ndarray, fast=12, slow=26, signal=9) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
def calc_bollinger(closes: np.ndarray, period=20, std_dev=2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
def calc_ma(closes: np.ndarray, period=20) -> np.ndarray: ...
def calc_ema(closes: np.ndarray, period=20) -> np.ndarray: ...
def calc_stochastic(highs, lows, closes, k=14, d=3) -> tuple[np.ndarray, np.ndarray]: ...
def calc_adx(highs, lows, closes, period=14) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
def calc_atr(highs, lows, closes, period=14) -> np.ndarray: ...
def calc_ichimoku(highs, lows, closes) -> dict[str, np.ndarray]: ...

# 신호 생성 함수들
def signals_rsi(closes) -> list[tuple[int, str]]: ...        # [(bar_idx, 'long'|'short'), ...]
def signals_macd(closes) -> list[tuple[int, str]]: ...
def signals_bollinger(closes) -> list[tuple[int, str]]: ...
def signals_ma(closes) -> list[tuple[int, str]]: ...
def signals_ema(closes) -> list[tuple[int, str]]: ...
def signals_volume(closes, volumes) -> list[tuple[int, str]]: ...
def signals_support_resistance(highs, lows, closes) -> list[tuple[int, str]]: ...
def signals_fibonacci(highs, lows, closes) -> list[tuple[int, str]]: ...
def signals_ichimoku(highs, lows, closes) -> list[tuple[int, str]]: ...
def signals_stochastic(highs, lows, closes) -> list[tuple[int, str]]: ...
def signals_trendline(closes) -> list[tuple[int, str]]: ...
def signals_adx(highs, lows, closes) -> list[tuple[int, str]]: ...
def signals_atr(highs, lows, closes) -> list[tuple[int, str]]: ...
```

**의존성:** `numpy` (이미 사용 중 여부 확인, 없으면 사용자 승인 후 설치)

---

### Task 2: 백테스트 실행 서비스

**파일:** `dashboard/backend/services/auto_backtest.py` (신규)

```python
async def run_backtest(symbol: str, horizon_h: int = 24, lookback: int = 500) -> dict:
    """
    coin_ohlcv_1h에서 데이터 로드 →
    13개 지표 신호 계산 →
    각 신호 발생 시점 기준 horizon_h 후 실제 가격으로 방향 적중 판정 →
    지표별 통계 반환
    """
```

반환 형식:
```json
{
  "symbol": "BTCUSDT",
  "horizon_h": 24,
  "lookback_bars": 500,
  "computed_at": "2026-04-19T...",
  "indicators": [
    {
      "name": "RSI",
      "signal_count": 42,
      "long_signals": 28,
      "short_signals": 14,
      "hit_count": 29,
      "hit_rate": 69.0,
      "avg_return_pct": 1.23,
      "max_win_pct": 8.4,
      "max_loss_pct": -3.1
    },
    ...
  ]
}
```

**캐시 로직:** 같은 symbol+horizon_h의 결과가 1시간 이내면 캐시 반환.

---

### Task 3: DB 마이그레이션

**파일:** `dashboard/backend/db/schema.sql` 에 `auto_backtest_cache` 테이블 추가
(schema.sql은 `CREATE TABLE IF NOT EXISTS` 방식으로 관리하므로 직접 추가)

---

### Task 4: API 엔드포인트

**파일:** `dashboard/backend/api/sim_routes.py` 에 추가

```
GET /api/sim/auto-backtest
  Query params:
    symbol: str = "BTCUSDT"
    horizon_h: int = 24  (4 | 8 | 24)
    lookback: int = 500
  Response: auto_backtest 결과 JSON
```

---

### Task 5: 프론트엔드 — 자동 백테스트 탭

**파일:** `dashboard/frontend/src/components/shared/AutoBacktest.tsx` (신규)

레이아웃:
```
┌─── 자동 백테스트 ──────────────────────────────────────────┐
│  심볼: [BTCUSDT ▼]  수평선: [24h ▼]  [분석 실행]           │
├────────────────────────────────────────────────────────────┤
│  지표       신호수  롱  숏  적중률   평균수익   최대익/손    │
│  RSI         42    28  14   69%    +1.23%   +8.4/-3.1%   │
│  MACD        31    20  11   58%    +0.67%   +5.2/-4.8%   │
│  ...                                                       │
├────────────────────────────────────────────────────────────┤
│  [Recharts 바 차트 — 적중률 시각화]                         │
└────────────────────────────────────────────────────────────┘
```

**Simulator.tsx** 에 "자동 백테스트" 탭 섹션으로 통합.

---

## 구현 순서

1. Task 3: schema.sql 수정 (기반)
2. Task 1: ta_indicators.py (계산 엔진)
3. Task 2: auto_backtest.py (백테스트 서비스)
4. Task 4: sim_routes.py 엔드포인트 추가
5. Task 5: AutoBacktest.tsx + Simulator 통합

---

## Acceptance Criteria

- [ ] 13개 지표 모두 신호 계산 동작 (numpy 기반)
- [ ] 심볼/수평선/롤백 기간 선택 가능
- [ ] 지표별 적중률, 신호 수, 평균 수익률 표시
- [ ] 1시간 캐시로 중복 계산 방지
- [ ] coin_ohlcv_1h 데이터 부족 시 명확한 에러 메시지
- [ ] Recharts 바 차트 시각화 (적중률 기준선 50% 표시)
- [ ] 기존 시뮬레이터 기능 회귀 없음

---

## 제약 / 주의사항

- `numpy` 의존성: 기존 사용 여부 확인 필요. 없으면 사용자 승인 후 설치.
- 데이터 부족: 최소 60봉(ADX, 일목균형표 계산 최소 요구량) 없으면 해당 지표 skip.
- 피보나치/지지저항은 근사 알고리즘 사용 (완벽한 트레이더 기준 아님, 단순 통계 목적).
- 백테스트 결과 ≠ 미래 수익 보장. UI에 면책 문구 표시.
