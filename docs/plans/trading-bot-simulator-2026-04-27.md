# 매매봇 시뮬레이터 v2 구현 계획

**작성일:** 2026-04-27
**기능:** 롱/숏 독립 점수 기반 자동 매매 시뮬레이터 (레버리지·수수료 포함)

---

## 1. 요구사항 요약

| 항목 | 결정값 |
|------|-------|
| 포지션 방향 | 롱 + 숏 (단일 포지션, 동시 보유 불가) |
| 점수 체계 | long_score / short_score 독립 계산 (합 ≠ 100) |
| 롱 진입 | long_score > 롱 임계값 (기본 70, UI 조절) |
| 숏 진입 | short_score > 숏 임계값 (기본 70, UI 조절) |
| 충돌 처리 | 양쪽 동시 임계값 초과 → 관망(flat) |
| Flip | 반대 점수 임계값 초과 시 즉시 청산 후 반대 진입 |
| 청산 우선순위 | SL > TP > Flip > 점수하락 > 기간종료 |
| 레버리지 | UI 설정 (기본 1x, 수익/손실 배수 적용) |
| 강제청산 | 자본 0 이하 시 즉시 청산, 시뮬레이션 종료 |
| 포지션 크기 | 10~100% UI 조절, 기본 100% |
| 수수료 | taker 0.06% (진입/청산 각 1회, Flip 시 3회) |
| 피라미딩 | v2 연기 (v1은 단일 진입) |
| 데이터 소스 | Bybit (ccxt, 기존 유지) |

---

## 2. 점수 계산 공식

### 2-1. long_score (강세 점수, 0~100)

```python
long_score = macro_bullish * 0.4 + tech_bullish * 0.6
```

- **macro_bullish**: 기존 공식 유지
  | level | score |
  |-------|-------|
  | bullish | 80 |
  | neutral | 55 |
  | bearish | 35 |
  | warning | 20 |
  | critical | 10 |

- **tech_bullish**: 기존 `calc_tech_bullish_score()` 유지 (RSI<30→85, MACD상향→75, BB하단→80, ADX상승→70)

### 2-2. short_score (약세 점수, 0~100)

```python
short_score = macro_bearish * 0.4 + tech_bearish * 0.6
macro_bearish = 100 - macro_bullish
```

- **tech_bearish**: 약세 지표 기반 별도 계산
  ```python
  def calc_tech_bearish_score(details: dict) -> float:
      scores = []
      # RSI (과매수 = 숏 강세)
      rsi = details.get("rsi")
      if rsi is not None:
          if rsi > 70:   scores.append(85.0)   # 과매수
          elif rsi > 55: scores.append(65.0)
          elif rsi > 40: scores.append(45.0)
          else:          scores.append(20.0)   # 과매도

      # MACD (하향 = 숏 강세)
      macd = details.get("macd")
      if macd is not None:
          hist = macd.get("histogram", 0) or 0
          prev = macd.get("prev_histogram", 0) or 0
          if hist < 0 and hist < prev:  scores.append(75.0)  # 하향 확대
          elif hist < 0:                scores.append(55.0)
          elif hist > 0 and hist > prev: scores.append(25.0) # 상향 확대
          else:                         scores.append(45.0)

      # BB (상단 근접 = 숏 강세)
      bb = details.get("bb")
      if bb is not None:
          if bb > 0.8:   scores.append(80.0)
          elif bb > 0.6: scores.append(60.0)
          elif bb > 0.4: scores.append(45.0)
          else:          scores.append(25.0)

      # ADX (강한 하락 추세 = 숏 강세)
      adx_data = details.get("adx")
      if adx_data is not None:
          adx = adx_data.get("adx", 0) or 0
          plus_di = adx_data.get("plus_di", 0) or 0
          minus_di = adx_data.get("minus_di", 0) or 0
          if adx > 25 and minus_di > plus_di: scores.append(70.0)
          elif adx > 25:                      scores.append(30.0)
          else:                               scores.append(50.0)

      return sum(scores) / len(scores) if scores else 50.0
  ```

---

## 3. 매매 로직

```python
for seq, idx in enumerate(target_indices):
    long_s  = calc_long_score(macro_bullish, tech_details)
    short_s = calc_short_score(macro_bullish, tech_details)
    both_triggered = long_s > long_th and short_s > short_th
    is_last = seq == len(target_indices) - 1

    if position is None:
        if not both_triggered:
            if long_s > long_th:
                # 롱 진입 (수수료 차감)
                capital_after_fee = capital * position_size_pct * (1 - FEE_RATE)
                position = {"direction": "long", "entry": close, ...}

            elif short_s > short_th:
                # 숏 진입 (수수료 차감)
                position = {"direction": "short", "entry": close, ...}

    else:
        reason = None
        d = position["direction"]
        entry = position["entry"]

        # 1위: SL
        if d == "long"  and close <= entry * (1 - sl_pct / 100): reason = "stop_loss"
        if d == "short" and close >= entry * (1 + sl_pct / 100): reason = "stop_loss"

        # 2위: TP
        elif d == "long"  and close >= entry * (1 + tp_pct / 100): reason = "take_profit"
        elif d == "short" and close <= entry * (1 - tp_pct / 100): reason = "take_profit"

        # 3위: Flip (반대 점수 초과)
        elif d == "long"  and short_s > short_th and not both_triggered: reason = "flip"
        elif d == "short" and long_s  > long_th  and not both_triggered: reason = "flip"

        # 4위: 점수 하락
        elif d == "long"  and long_s  <= long_th:  reason = "score_exit"
        elif d == "short" and short_s <= short_th: reason = "score_exit"

        # 5위: 기간 종료
        elif is_last: reason = "period_end"

        if reason:
            pnl = calc_pnl(d, entry, close, leverage, position_size_pct)
            pnl -= FEE_RATE  # 청산 수수료
            capital *= (1 + pnl / 100)

            # 자본 0 이하 → 강제청산(liquidation) 후 종료
            if capital <= 0:
                capital = 0
                break

            if reason == "flip":
                # Flip: 즉시 반대 진입 (수수료 추가 차감)
                new_dir = "short" if d == "long" else "long"
                capital *= (1 - FEE_RATE)
                position = {"direction": new_dir, "entry": close, ...}
            else:
                position = None
```

### 손익 계산

```python
def calc_pnl(direction, entry, exit_price, leverage, size_pct) -> float:
    if direction == "long":
        raw = (exit_price - entry) / entry
    else:
        raw = (entry - exit_price) / entry
    return raw * leverage * 100   # % 반환
```

> **주의**: 레버리지는 수익률 계산에만 적용. 실제 포지션/청산가 계산 없음.
> 자본 × (1 + pnl% / 100) 로 자산 갱신.

---

## 4. API 스펙

### Request

```
POST /api/sim/composite-backtest
```

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "start_date": "2024-01-01",
  "end_date": "2024-06-30",
  "stop_loss_pct": 3.0,
  "take_profit_pct": 5.0,
  "long_threshold": 70.0,
  "short_threshold": 70.0,
  "leverage": 1.0,
  "position_size_pct": 100.0,
  "initial_capital": 10000.0
}
```

### Response

```json
{
  "summary": {
    "total_return_pct": 12.3,
    "win_rate": 0.62,
    "trade_count": 13,
    "long_trade_count": 8,
    "short_trade_count": 5,
    "winning_trades": 8,
    "losing_trades": 5,
    "max_drawdown_pct": -4.2,
    "final_capital": 11230.0,
    "liquidated": false
  },
  "trades": [
    {
      "type": "entry",
      "direction": "long",
      "timestamp": "2024-01-15T09:00:00Z",
      "price": 42000.0,
      "pnl_pct": null,
      "reason": null,
      "long_score": 74.2,
      "short_score": 31.5
    },
    {
      "type": "exit",
      "direction": "long",
      "timestamp": "2024-01-18T14:00:00Z",
      "price": 44100.0,
      "pnl_pct": 5.0,
      "reason": "take_profit",
      "long_score": 55.1,
      "short_score": 48.2
    }
  ],
  "equity_curve": [
    {"timestamp": "2024-01-01T00:00:00Z", "value": 10000.0}
  ],
  "params": {
    "symbol": "BTCUSDT",
    "interval": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "stop_loss_pct": 3.0,
    "take_profit_pct": 5.0,
    "long_threshold": 70.0,
    "short_threshold": 70.0,
    "leverage": 1.0,
    "position_size_pct": 100.0,
    "macro_level": "bearish",
    "macro_bullish_score": 35.0
  }
}
```

---

## 5. UI 설계

```
┌──────────────────────────────────────────────────────────────┐
│ 종합 자동 백테스트                                             │
│                                                              │
│  심볼: [BTCUSDT ▼]  캔들: [1h ▼]                             │
│  기간: [2024-01-01] ~ [2024-06-30]                           │
│                                                              │
│  롱 임계값: [70]   숏 임계값: [70]                             │
│  손절: [3.0]%   익절: [5.0]%                                  │
│  레버리지: [1x]   포지션 크기: [100]%   초기자본: [10000]       │
│                                                              │
│  [🚀 테스트 실행]                                             │
└──────────────────────────────────────────────────────────────┘

┌──────────┐ ┌──────────┐ ┌────────────────────────────────────┐
│ 총 수익률 │ │ 승률      │ │ 거래 횟수                           │
│ +12.3%   │ │ 62%      │ │ 13회 (롱 8 / 숏 5)                  │
└──────────┘ └──────────┘ └────────────────────────────────────┘

[자본 곡선 차트 (에쿼티 커브) — nice-to-have]

[거래 내역 테이블]
 날짜         | 방향 | 가격    | 수익률 | 사유    | L점수 | S점수
 2024-01-15  | 🟢롱 | $42,000 |  -     | -       | 74.2  | 31.5
 2024-01-18  | 🔴청산| $44,100 | +5.0%  | 익절    | 55.1  | 48.2
 2024-01-20  | 🔴숏 | $43,500 |  -     | -       | 28.3  | 72.1
```

---

## 6. 파일 변경 목록

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `dashboard/backend/services/composite_backtest.py` | 수정 | 롱/숏 독립 점수, Flip, 레버리지, 수수료, 강제청산 |
| `dashboard/backend/api/sim_routes.py` | 수정 | Request 모델 확장 (새 파라미터 추가) |
| `dashboard/frontend/src/components/shared/CompositeSimulator.tsx` | 수정 | UI 파라미터 추가, 롱/숏 구분 표시 |

---

## 7. 구현 태스크

### Task 1: 백엔드 — 점수 계산 및 매매 로직 재설계

**파일:** `dashboard/backend/services/composite_backtest.py`

1. `calc_tech_bearish_score(details)` 함수 추가 (RSI>70=85, MACD하향=75, BB상단=80, ADX하락=70)
2. `calc_short_score(macro_bullish, tech_details)` 함수 추가
3. `CompositeBacktestParams` 확장:
   - `long_threshold: float = 70.0`
   - `short_threshold: float = 70.0`
   - `leverage: float = 1.0`
   - `position_size_pct: float = 100.0`
4. `_run_backtest_sync()` 매매 루프 재작성:
   - long_score / short_score 양쪽 계산
   - 충돌(both > threshold) → 관망
   - 청산 우선순위: SL > TP > Flip > 점수하락 > 기간종료
   - Flip: 청산 수수료 + 진입 수수료 즉시 적용
   - 자본 0 이하 → `liquidated=True`, 루프 종료
5. 결과 dict에 `long_trade_count`, `short_trade_count`, `liquidated` 추가
6. 거래 로그: `direction`, `long_score`, `short_score` 필드 추가

### Task 2: 백엔드 — API 라우트 확장

**파일:** `dashboard/backend/api/sim_routes.py`

1. `CompositeBacktestRequest` 모델에 필드 추가:
   - `long_threshold: float = Field(default=70.0, ge=1, le=99)`
   - `short_threshold: float = Field(default=70.0, ge=1, le=99)`
   - `leverage: float = Field(default=1.0, ge=1, le=100)`
   - `position_size_pct: float = Field(default=100.0, gt=0, le=100)`
   - `initial_capital: float = Field(default=10000.0, gt=0)`
2. `CompositeBacktestParams` 생성 시 새 필드 전달

### Task 3: 프론트엔드 — UI 파라미터 확장

**파일:** `dashboard/frontend/src/components/shared/CompositeSimulator.tsx`

1. 새 state 추가: `longThreshold`, `shortThreshold`, `leverage`, `positionSizePct`, `initialCapital`
2. 설정 패널 행 추가:
   - 행 2: 롱 임계값, 숏 임계값
   - 행 3: 손절%, 익절%
   - 행 4: 레버리지, 포지션 크기%, 초기자본
3. 결과 카드: 거래 횟수에 롱/숏 분리 표시
4. 거래 테이블:
   - `direction` 컬럼: 🟢 롱진입 / 🔴 숏진입 / 청산 표시
   - `long_score`, `short_score` 컬럼 추가
   - 청산 사유 한국어 매핑: flip→"포지션전환", score_exit→"점수이탈"
5. `liquidated=true` 시 경고 배지 표시

---

## 8. 제한 사항

- **매크로 점수 정적 적용**: 현재 시점 매크로가 전 기간에 적용됨 (역사적 재현 불가). UI 주의 문구 유지.
- **레버리지**: 수익 배수만 적용. 실제 마진/청산가 계산 없음.
- **피라미딩 미지원**: 단일 포지션만. 분할 진입은 v2.
- **수수료**: taker 0.06% 고정. 메이커 할인 미지원.
