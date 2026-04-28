# Trading Bot Simulator 개선 계획

**작성일:** 2026-04-27  
**배경:** ouroboros 인터뷰로 진단한 구조적 문제 해결 — 승률 56.3%에도 수익률 -19.29% 발생  
**목표:** 동일 조건(BTCUSDT 1h, 2026-04-01~04-30) 기준 수익률 +10% 이상

---

## 진단된 문제

| 문제 | 영향 |
|------|------|
| score_exit 임계값 = 진입 임계값 | 진입 직후 점수 소폭 하락 시 즉시 청산 → 수익 거래의 실현 이익 미미 |
| 캔들 종가 기준 SL/TP 체크 | 캔들 내 SL 가격 도달 시 종가까지 추가 하락분 손실 반영 → R:R 악화 |
| Bearish 매크로에서 Long 미차단 | 불리한 방향 롱 진입 혼입 |

---

## Task 1: composite_backtest.py — 3가지 구조 개선

**파일:** `dashboard/backend/services/composite_backtest.py`

### 1-1. score_exit_buffer 파라미터 추가

`CompositeBacktestParams`에 추가:
```python
score_exit_buffer: float = 15.0  # exit 기준 = threshold - buffer
```
`__post_init__` 검증: `0 <= score_exit_buffer < 100`

score_exit 로직 변경:
```python
# 기존
if direction == "long" and long_score <= long_threshold:
    reason = "score_exit"

# 신규
exit_threshold_long = long_threshold - params.score_exit_buffer
exit_threshold_short = short_threshold - params.score_exit_buffer
if direction == "long" and long_score <= exit_threshold_long:
    reason = "score_exit"
elif direction == "short" and short_score <= exit_threshold_short:
    reason = "score_exit"
```

### 1-2. SL/TP — 캔들 고가/저가 기반 체결 (정확한 R:R)

`_run_backtest_sync` 루프에서 `high`/`low` 값 추출:
```python
high = float(candle_row["high"])
low = float(candle_row["low"])
```

SL/TP 판단을 close 대신 high/low로:
```python
sl_price_long = entry * (1 - params.stop_loss_pct / 100)
tp_price_long = entry * (1 + params.take_profit_pct / 100)

if direction == "long":
    if low <= sl_price_long:          # 저가가 SL 가격에 닿음
        reason = "stop_loss"
        exit_price = sl_price_long    # 정확한 SL 가격에 체결
    elif high >= tp_price_long:       # 고가가 TP 가격에 닿음
        reason = "take_profit"
        exit_price = tp_price_long    # 정확한 TP 가격에 체결
    else:
        exit_price = close            # SL/TP 미도달 시 종가
```

Short도 동일하게 적용:
```python
sl_price_short = entry * (1 + params.stop_loss_pct / 100)
tp_price_short = entry * (1 - params.take_profit_pct / 100)

if direction == "short":
    if high >= sl_price_short:
        reason = "stop_loss"
        exit_price = sl_price_short
    elif low <= tp_price_short:
        reason = "take_profit"
        exit_price = tp_price_short
    else:
        exit_price = close
```

PnL 계산에 `close` 대신 `exit_price` 사용:
```python
if direction == "long":
    raw_return = (exit_price - entry) / entry
else:
    raw_return = (entry - exit_price) / entry
```

Flip/score_exit/period_end 청산 시에는 `exit_price = close` 유지.

### 1-3. Bearish 매크로 롱 진입 차단

진입 판단 블록에서:
```python
elif long_score > long_threshold:
    # bearish 매크로(macro_bullish < 40)면 롱 진입 차단
    if macro_bullish >= 40:
        # 롱 진입 실행 (기존 코드)
        ...
```

---

## Task 2: sim_routes.py + CompositeSimulator.tsx — score_exit_buffer 파라미터 추가

### 2-1. sim_routes.py

`CompositeBacktestRequest`에 추가:
```python
score_exit_buffer: float = Field(default=15.0, ge=0, lt=100, description="score_exit 완충값 (exit = threshold - buffer)")
```

`composite_backtest_endpoint`에서 전달:
```python
score_exit_buffer=req.score_exit_buffer,
```

### 2-2. CompositeSimulator.tsx

state 추가:
```typescript
const [scoreExitBuffer, setScoreExitBuffer] = useState(15)
```

행 3 입력 필드 추가 (기존 입력들 뒤에):
```tsx
<label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
  <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>청산버퍼:</span>
  <input
    type="number"
    value={scoreExitBuffer}
    step={5}
    min={0}
    max={50}
    onChange={(e) => setScoreExitBuffer(Number(e.target.value))}
    style={numberInputStyle}
  />
  <span style={{ color: '#475569', fontSize: '0.78rem' }}>pt</span>
</label>
```

API 요청에 추가:
```json
score_exit_buffer: scoreExitBuffer,
```

---

## 파일 변경 목록

| 파일 | 변경 |
|------|------|
| `dashboard/backend/services/composite_backtest.py` | score_exit_buffer, high/low SL/TP, 매크로 필터 |
| `dashboard/backend/api/sim_routes.py` | score_exit_buffer 필드 추가 |
| `dashboard/frontend/src/components/shared/CompositeSimulator.tsx` | 청산버퍼 입력 추가 |

---

## 기대 효과

| 개선 | 예상 영향 |
|------|---------|
| score_exit_buffer=15 | 진입 55→청산 40: score_exit 조기청산 대폭 감소 |
| high/low SL/TP | 정확한 R:R 실현, TP 미스 감소 |
| 매크로 롱 차단 | Bearish 구간 불필요한 롱 제거 |
