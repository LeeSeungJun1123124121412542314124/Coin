# 백테스트 자동 튜닝 Runbook

**범위:** `dashboard/backend/services/backtest_tuner.py` + `/sim/tune` API + UI 자동 튜닝 패널.
**선행 plan:** `docs/plans/backtest-tuning-infra-2026-04-28.md` (이 plan 구현체의 사용 가이드).

---

## 1. 시스템 한 줄 요약

전체 OHLCV 데이터를 1회 fetch → 9개 expanding window로 분할 → 각 window 안에서 Optuna TPE로
**12 파라미터(임계값 3 + SL/TP 2 + 포지션 2 + macro/tech 비율 1 + RSI/MACD/BB/ADX 가중치 4)** 를
탐색해 IS expectancy 최대 → best params를 **OOS 기간**에 적용 → 9 windows OOS 평균으로 최종 평가.

---

## 2. 사용 흐름 (UI)

1. 대시보드의 "종합 자동 백테스트" 섹션 → 심볼/캔들/기간/초기자본 설정.
2. 그 아래 보라색 패널에서 **"🚀 자동 튜닝 시작"** 클릭 (윈도우당 trials, 윈도우 수 조정 가능).
3. 5초 간격 자동 폴링으로 진행률 갱신: `Window N/9, Trial M/200`.
4. 완료 시 상단에 ✅/❌ 필터 통과 배지 + OOS 평균 메트릭 카드.
5. 하단 "상위 10 조합" 테이블에서 한 행 클릭 → 입력 패널의 7개 핵심 파라미터가 자동 갱신
   → "🚀 테스트 실행"으로 동일 조합을 단일 백테스트로 재현해 자본곡선 확인.

---

## 3. 사용 흐름 (API)

```bash
# 1) 튜닝 시작
curl -X POST http://localhost:8000/api/sim/tune \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "interval": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "n_trials": 200,
    "n_windows": 9
  }'
# → {"job_id": "uuid...", "status": "queued"}

# 2) 진행률 폴링
curl http://localhost:8000/api/sim/tune/{job_id}
# → status: queued | running | completed | failed
```

결과 파일은 `backtest/results/tuning/{job_id}.json`에 원자적으로 저장되며, 매 10 trial마다
`progress` 필드가 갱신된다. 동일 파일을 GET 응답으로 그대로 반환한다.

---

## 4. 결과 해석

### 4-1. ✅ 필터 통과(`passes_filter: true`)

**의미:** 9 windows OOS 평균이 다음을 모두 충족함:
- `avg_oos_expectancy > 0`
- `avg_oos_profit_factor ≥ 1.5`
- `avg_oos_mdd ≤ 25%`
- `avg_oos_trade_count ≥ 30`

**다음 액션:** "꾸준히 수익 나는 베이스라인" 확보됨. 후속 plan으로 진행:
- 다른 심볼/타임프레임 확장 (ETH, 4h)
- 승률 끌어올리기 (지표 신호 임계값 미세 조정 또는 신규 booster 추가)
- 페이퍼 트레이딩 / 실시간 자동매매 연결 검토

### 4-2. ❌ 필터 미통과

**가능한 원인 진단:**

| 증상 | 의미 | 다음 액션 |
|------|------|-----------|
| 모든 trial의 PF < 1.5 | 신호 체계 자체가 알파가 부족 | 지표 재설계 (ATR/Volume spike 추가, ML 신호) — 별도 plan |
| trade_count < 30 | 임계값이 너무 빡빡 | n_trials 늘리거나 threshold 탐색 하한 확장 |
| MDD > 25% | 손실 통제 부족 | leverage 상한 더 낮추거나 SL 탐색 하한 더 타이트하게 |
| IS expectancy ≫ OOS expectancy | 과적합 (in-sample 곡선 맞추기) | 더 많은 데이터(2년+) 또는 windows 수 늘림 |

**중요:** 필터 미통과 상태에서 "trial 수를 더 늘려서 우연히 맞추는" 시도는 금지. 그건 정의상
백테스트 곡선 맞추기이며 실전에서 깨진다. plan의 acceptance 결정 트리를 따를 것.

### 4-3. IS vs OOS 격차 해석

`is_metrics`(각 window의 IS best)와 `oos_metrics`(같은 params를 OOS 1개월에 적용)를
비교해서 격차 측정.

| 격차 | 해석 |
|------|------|
| OOS expectancy ≥ IS의 70% | 일반화 양호 — 안정적 신호 |
| OOS expectancy 30~70% | 부분 일반화 — 보수적으로 사용 가능, 추가 검증 권장 |
| OOS expectancy < 30% 또는 음수 | 강한 과적합 — 그 조합은 실전 부적합 |

윈도우별로 격차가 들쭉날쭉하면 신호 자체가 시장 레짐 변화에 취약. 평균 격차로만 판단하지 말 것.

---

## 5. 재현성 보장

- Optuna `TPESampler(seed=42)` 고정 — 동일 데이터·파라미터로 동일 결과.
- 단, `_fetch_ohlcv`가 ccxt에서 라이브 데이터를 가져오므로 호출 시점에 따라 마지막 봉이 달라질 수 있음.
  완전 재현이 필요하면 결과 JSON의 `config.start_date`/`config.end_date`를 명시적으로 같은 값으로 고정.
- 결과 파일은 `backtest/results/tuning/{job_id}.json`에 원자적 쓰기로 저장 — git에 커밋하지 않음
  (대용량, 반복 생성 자산).

---

## 6. 알려진 한계

1. **단일 심볼 단일 타임프레임** — BTCUSDT 1h 외 확장은 후속 plan 범위.
2. **macro_bullish 단일 값** — 윈도우 전체에 동일한 매크로 점수 적용. 시점별 매크로 변동은
   미반영(plan 단순화).
3. **단일 thread Optuna study** — `study.optimize()`는 thread pool 1개로 직렬 실행. CPU 8코어
   머신에서 활용도 낮음. 후속에서 `n_jobs` 또는 `ProcessPoolExecutor` 분리 검토.
4. **승률 단독 끌어올리기 시 곡선 맞추기 위험** — 이 인프라는 "수익성 베이스라인"을 위한 도구.
   70%+ 승률만 단독 추구하면 백테스트에서만 좋고 실전에서 깨진다 (plan §1 진단 참조).

---

## 7. 자주 보는 운영 이슈

| 증상 | 원인 | 해결 |
|------|------|------|
| `OHLCV 데이터 수집 실패` | Bybit API 일시 오류 또는 ccxt 미설정 | 재시도, `crypto-volatility-bot/app/data/data_collector.py` 확인 |
| `expanding window 생성 실패 — 데이터 기간 부족` | start/end 기간이 너무 짧음 | 최소 4개월(IS 3 + OOS 1) 이상 보장 |
| 진행률이 0%에 멈춤 | BackgroundTask thread 풀이 막힘 | uvicorn worker 수 확인, FastAPI thread pool 크기 조정 |
| 필터 통과 조합 0개 | 신호 알파 부족 또는 기간 짧음 | `n_trials` 늘림 → 그래도 0이면 신호 체계 재검토 |

---

## 8. 코드 진입점 (디버깅용)

```python
# 단일 호출로 로컬에서 walk-forward 실행 (Python REPL)
from dashboard.backend.services.composite_backtest import CompositeBacktestParams
from dashboard.backend.services.backtest_tuner import run_walk_forward
import uuid

base = CompositeBacktestParams(
    symbol="BTC/USDT", interval="1h",
    start_date="2024-01-01", end_date="2024-12-31",
    initial_capital=10000.0,
)
result = run_walk_forward(str(uuid.uuid4()), base, n_trials=50, n_windows=9)
print(result["aggregate"])
```

빠른 smoke test용으로 `n_trials=20`도 가능. 단 너무 적으면 TPE가 충분히 학습 못 함
(`n_startup_trials=20`이 기본).
