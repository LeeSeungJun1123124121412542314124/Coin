# 종합 자동 트레이딩 시뮬레이터 구현 계획

**작성일:** 2026-04-27  
**기능:** 매크로 + 기술 지표 종합 점수 기반 자동 매매 시뮬레이션

---

## 1. 요구사항 요약

| 항목 | 결정값 |
|------|-------|
| 전략 결합 | 점수 합산: macro × 0.4 + tech × 0.6 |
| 매수 임계값 | composite > 70 |
| 매도 임계값 | composite < 30 (또는 손절/익절 조건) |
| 기술 지표 | RSI, MACD, 볼린저밴드, ADX |
| 캔들 단위 | 사용자 선택 (1h / 4h / 1d) |
| 기간 | 사용자가 시작일~종료일 직접 설정 |
| 포지션 | 단일 포지션 (한 번에 1개) |
| 리스크 관리 | 손절 % + 익절 % 설정 (둘 중 먼저 도달하는 조건 실행) |
| 기간 종료 | 미청산 포지션 자동 매도 |
| 결과 지표 | 총 수익률, 승률/거래 횟수, 거래 내역 타임라인 |

---

## 2. 아키텍처

```
[CompositeSimulator.tsx]
  └── POST /api/sim/composite-backtest
        └── composite_backtest.py
              ├── DataCollector.fetch_ohlcv()       ← OHLCV 히스토리
              ├── TechnicalAnalyzer.analyze()        ← 캔들별 기술 점수
              └── research_analyzer._analyze_macro() ← 매크로 점수 (캐시)
```

---

## 3. 점수 정규화 로직

### 3-1. 매크로 불리시 점수 (macro_bullish: 0~100)

`research_analyzer._analyze_macro()`의 `level` 필드 활용:

| level | macro_bullish |
|-------|--------------|
| bullish | 80 |
| neutral | 55 |
| bearish | 35 |
| warning | 20 |
| critical | 10 |

### 3-2. 기술적 불리시 점수 (tech_bullish: 0~100)

`TechnicalAnalyzer.analyze()` details에서 RSI, MACD, BB, ADX 추출:

```python
def calc_tech_bullish_score(details: dict) -> float:
    scores = []

    # RSI (과매도=강세, 과매수=약세)
    rsi = details.get("rsi")
    if rsi is not None:
        if rsi < 30:   scores.append(85)
        elif rsi < 45: scores.append(65)
        elif rsi < 60: scores.append(45)
        else:          scores.append(20)

    # MACD (방향 기반)
    macd = details.get("macd", {})
    if isinstance(macd, dict):
        hist = macd.get("histogram", 0) or 0
        prev = macd.get("prev_histogram", 0) or 0
        if hist > 0 and hist > prev:   scores.append(75)  # 상향 확대
        elif hist > 0:                 scores.append(55)  # 양수 유지
        elif hist < 0 and hist < prev: scores.append(25)  # 하향 확대
        else:                          scores.append(45)

    # 볼린저밴드 (하단 근접=강세 기회)
    bb = details.get("bb")
    if bb is not None:
        if bb < 0.2:   scores.append(80)  # 하단 근접
        elif bb < 0.4: scores.append(60)
        elif bb < 0.6: scores.append(45)
        else:          scores.append(25)  # 상단 근접

    # ADX (추세 강도 — 방향은 MACD로 판단, 강도만 반영)
    adx_data = details.get("adx", {})
    if isinstance(adx_data, dict):
        adx_val = adx_data.get("adx", 0) or 0
        plus_di = adx_data.get("plus_di", 0) or 0
        minus_di = adx_data.get("minus_di", 0) or 0
        if adx_val > 25 and plus_di > minus_di:  scores.append(70)
        elif adx_val > 25:                        scores.append(30)
        else:                                     scores.append(50)  # 추세 약함

    return sum(scores) / len(scores) if scores else 50.0
```

### 3-3. 복합 점수

```python
composite = macro_bullish * 0.4 + tech_bullish * 0.6
```

---

## 4. 매매 로직

```python
for i, candle in enumerate(candles_in_range):
    composite = calc_composite(candle_window, macro_level)

    if position is None:
        if composite > 70:
            # 매수 진입
            position = {"entry_price": close, "timestamp": ts, "score": composite}

    else:
        exit_reason = None

        # 손절
        if close <= position["entry_price"] * (1 - stop_loss_pct / 100):
            exit_reason = "stop_loss"

        # 익절
        elif close >= position["entry_price"] * (1 + take_profit_pct / 100):
            exit_reason = "take_profit"

        # 시그널 역전
        elif composite < 30:
            exit_reason = "score_signal"

        # 기간 마지막 캔들
        elif i == len(candles_in_range) - 1:
            exit_reason = "period_end"

        if exit_reason:
            pnl_pct = (close - position["entry_price"]) / position["entry_price"] * 100
            trades.append({"type": "sell", "pnl_pct": pnl_pct, "reason": exit_reason, ...})
            position = None
```

---

## 5. API 스펙

### Request

```
POST /api/sim/composite-backtest
Content-Type: application/json
```

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "start_date": "2024-01-01",
  "end_date": "2024-06-30",
  "stop_loss_pct": 3.0,
  "take_profit_pct": 5.0
}
```

### Response

```json
{
  "summary": {
    "total_return_pct": 12.3,
    "win_rate": 0.62,
    "trade_count": 13,
    "winning_trades": 8,
    "losing_trades": 5,
    "max_drawdown_pct": -4.2,
    "final_capital": 11230.0
  },
  "trades": [
    {
      "type": "buy",
      "timestamp": "2024-01-15T09:00:00Z",
      "price": 42000.0,
      "pnl_pct": null,
      "reason": null,
      "composite_score": 74.2
    },
    {
      "type": "sell",
      "timestamp": "2024-01-18T14:00:00Z",
      "price": 44100.0,
      "pnl_pct": 5.0,
      "reason": "take_profit",
      "composite_score": 38.5
    }
  ],
  "equity_curve": [
    {"timestamp": "2024-01-01T00:00:00Z", "value": 10000.0},
    {"timestamp": "2024-01-02T00:00:00Z", "value": 10000.0}
  ],
  "params": {
    "symbol": "BTCUSDT",
    "interval": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "stop_loss_pct": 3.0,
    "take_profit_pct": 5.0,
    "macro_level": "neutral",
    "macro_bullish_score": 55.0
  }
}
```

---

## 6. 프론트엔드 UI 설계

### 위치

`Simulator.tsx`에 탭 추가:
- 탭 A: **종합 시뮬레이션** (새로 만들 기능, 기본 선택)
- 탭 B: **지표별 분석** (기존 AutoBacktest, 유지)

### 종합 시뮬레이션 탭 구성

```
┌─────────────────────────────────────────────────────┐
│ 설정                                                  │
│  심볼: [BTCUSDT ▼]  캔들: [1h ▼]                     │
│  기간: [2024-01-01] ~ [2024-06-30]                   │
│  손절: [3.0]%   익절: [5.0]%                          │
│  [테스트 실행]                                         │
└─────────────────────────────────────────────────────┘

┌──────────┐ ┌──────────┐ ┌──────────────────────────┐
│ 총 수익률 │ │ 승률      │ │ 거래 횟수                 │
│ +12.3%   │ │ 62%       │ │ 13회 (8승 5패)            │
└──────────┘ └──────────┘ └──────────────────────────┘

[자본 곡선 차트 — Recharts LineChart]
 $12,000 ─────────────────────╮
 $11,000 ─────────╮           │
 $10,000 ─────────────────────╯

[거래 내역 타임라인]
 날짜         | 유형 | 가격    | 수익률 | 사유
 2024-01-15  | 매수 | $42,000 |  -     | score 74.2
 2024-01-18  | 매도 | $44,100 | +5.0%  | 익절
 ...
```

---

## 7. 구현 태스크

### Task 1: 백엔드 서비스 생성

**파일:** `dashboard/backend/services/composite_backtest.py`

1. `CompositeBacktestParams` dataclass 정의
2. `calc_tech_bullish_score(details)` 함수 (RSI/MACD/BB/ADX 점수화)
3. `calc_macro_bullish_score(level)` 함수 (level → 0~100)
4. `run_composite_backtest(params)` async 함수:
   - DataCollector.fetch_ohlcv로 워밍업 포함 데이터 수집
   - 매크로 분석 (`_analyze_macro()` 직접 호출, 캐시 활용)
   - 캔들별 슬라이딩 윈도우 TA 계산
   - 매매 로직 실행
   - equity_curve 계산 (캔들마다 현재 자산 가치 기록)
   - MDD 계산
   - 결과 dict 반환

### Task 2: API 라우트 추가

**파일:** `dashboard/backend/api/sim_routes.py`

1. `CompositeBacktestRequest` Pydantic 모델 추가
2. `POST /api/sim/composite-backtest` 엔드포인트 추가
3. 실행 시간이 길 수 있으므로 타임아웃 주의 (1h 캔들 6개월 ≈ ~4400개 캔들 × TA 연산)

### Task 3: 프론트엔드 컴포넌트 생성

**파일:** `dashboard/frontend/src/components/shared/CompositeSimulator.tsx`

1. 설정 패널: 심볼, 기간(시작/종료), 캔들 단위, 손절/익절 % 입력
2. 실행 버튼 + 로딩 상태
3. 결과 요약 카드 (총 수익률, 승률, 거래 횟수)
4. 자본 곡선 LineChart (Recharts)
5. 거래 내역 테이블 (날짜, 매수/매도, 가격, 수익률, 사유)

### Task 4: Simulator.tsx에 탭 통합

**파일:** `dashboard/frontend/src/components/screens/Simulator.tsx`

1. 상단에 탭 추가 ("종합 시뮬레이션" | "지표별 분석")
2. "종합 시뮬레이션" 탭에 `<CompositeSimulator />` 렌더링
3. "지표별 분석" 탭에 기존 `<AutoBacktest />` 유지

---

## 8. 파일 변경 목록

| 파일 | 변경 유형 |
|------|---------|
| `dashboard/backend/services/composite_backtest.py` | 신규 생성 |
| `dashboard/backend/api/sim_routes.py` | 수정 (엔드포인트 추가) |
| `dashboard/frontend/src/components/shared/CompositeSimulator.tsx` | 신규 생성 |
| `dashboard/frontend/src/components/screens/Simulator.tsx` | 수정 (탭 추가) |

---

## 9. 제한 사항 및 주의

- **매크로 점수는 현재 시점 기준 정적 적용:** 역사적 특정 시점의 매크로 환경을 재현하지 않음.  
  즉, 2024년 1월 시뮬레이션에도 현재 매크로 레벨이 적용됨. 이 한계를 UI에 표시 권장.
- **TechnicalAnalyzer 동기 연산:** 캔들 수가 많으면(예: 1h × 6개월 ≈ 4,380개) 응답 시간이 길어질 수 있음.  
  `run_in_executor`로 스레드 풀 처리 필요.
- **데이터 한계:** ccxt fetch_ohlcv는 거래소 limit에 따라 한 번에 1,000~1,500개만 반환.  
  긴 기간은 페이지네이션 루프 또는 limit 조정 필요.
