# 백테스트 자동 튜닝 인프라 + Walk-Forward 검증

**작성일:** 2026-04-28
**작성 방식:** ouroboros 인터뷰(Path B 직접 모드)로 모호성 좁힌 후 spec화
**선행 plan:** `docs/plans/backtest-improvement-2026-04-27.md` (이미 모두 구현 완료, 커밋 aa27aee~4886fed)

---

## 1. Context (왜 이 작업을 하는가)

### 직전 plan 점검 결과

`backtest-improvement-2026-04-27.md`의 3가지 개선은 모두 do 단계에서 구현·머지됨:

| 항목 | 커밋 |
|------|------|
| score_exit_buffer 파라미터 | 255a784 / f6f3f37 / 26620e2 |
| 캔들 high/low 기반 SL/TP | aa27aee |
| Bearish 매크로에서 Long 차단 | aa27aee |
| API params 동기화 | 4886fed |

이 plan은 **다음 단계**다. 이미 구현된 파라미터를 어떻게 "수익이 나는 조합"으로 자동 탐색할지의 인프라를 만든다.

### 진단된 본질 문제

현재 시뮬레이션은 **승률 56.3%인데 누적 수익률 -19.29%**. 즉 평균 손실이 평균 수익보다 크다 — 손익비(R:R) 문제이지 단순 승률 문제가 아니다. 따라서 이번 plan의 1차 목표는 "승률 끌어올리기"가 아니라 **양의 기대값(expectancy>0) + profit_factor ≥ 1.8 + MDD ≤ 25%** 를 만족하는 파라미터 조합을 찾는 것이다.

### 현재 인프라의 빈 곳

- **자동 튜닝 인프라 없음** — 모든 임계값·가중치를 `config/technical.yaml`과 UI 입력으로 수작업 조정
- **과적합 방지 장치 없음** — train/test 분할 X, walk-forward X. 백테스트 수치 자체가 신뢰성을 보증하지 못함

이 두 가지를 해결하지 않으면 어떤 튜닝도 "백테스트에서만 좋고 실전에서 깨지는" 곡선맞추기로 전락한다.

---

## 2. 결정된 Spec (인터뷰 결과)

| 트랙 | 결정 |
|------|------|
| 튜닝 범위 | 핵심 5개 + 포지션 2개 + 지표 가중치 5개 = **12 파라미터** |
| 최적화 알고리즘 | **Optuna TPE 베이지안** (200~300 trials) — 신규 의존성 1개 추가 (사용자 승인됨) |
| 목적함수 | **Expectancy 내림차순 + 필터** (PF ≥ 1.5 AND MDD ≤ 25% AND trade_count ≥ 30) |
| 검증 전략 | **Expanding window** — IS 3개월 시작 → 11개월까지, OOS 1개월, 총 **9 windows** |
| 인프라 | FastAPI **BackgroundTasks** + **ProcessPoolExecutor** + **JSON 파일 저장** |
| Acceptance | OOS 9 windows **평균 expectancy > 0** AND PF ≥ 1.5 AND MDD ≤ 25% 조합을 **최소 1개** 발견 |
| Non-goals | **다른 심볼·타임프레임 제외** (BTCUSDT 1h만, ETH·4h·15m 등은 후속 plan) |

### 튜닝 12 파라미터 상세

> **[2026-04-28 갱신]** 코드 검토 후 시정: composite_backtest.py는 ATR/BB width/CVI/HV/Volume spike가 아닌 **RSI/MACD/BB(%B)/ADX** 기반 단순 평균 시스템이며, technical_analyzer.py와는 별개. 따라서 튜닝 대상 가중치를 시뮬레이터 실제 사용 지표(RSI/MACD/BB/ADX)로 정정. macro/tech 비율(현재 0.4/0.6 고정)도 튜닝 대상에 포함.

| 그룹 | 파라미터 | 탐색 범위 |
|------|----------|----------|
| 진입 | `long_threshold` | 60 ~ 85 (int) |
| 진입 | `short_threshold` | 60 ~ 85 (int) |
| 청산 | `score_exit_buffer` | 5 ~ (threshold-1) (int) |
| 손절/익절 | `stop_loss_pct` | 1.0 ~ 5.0 (float) |
| 손절/익절 | `take_profit_pct` | 2.0 ~ 10.0 (float) |
| 포지션 | `position_size_pct` | 5 ~ 30 (float) |
| 포지션 | `leverage` | 1 ~ 5 (int) |
| 점수 비율 | `macro_weight` | 0.2 ~ 0.6 (float) — tech_weight = 1 - macro_weight |
| 지표 가중치 | `weight_rsi` | 0.0 ~ 1.0 (float) |
| 지표 가중치 | `weight_macd` | 0.0 ~ 1.0 (float) |
| 지표 가중치 | `weight_bb` | 0.0 ~ 1.0 (float) |
| 지표 가중치 | `weight_adx` | 0.0 ~ 1.0 (float) |

4개 지표 가중치는 trial 시점에 합이 1.0이 되도록 정규화. 모두 0이거나 음수가 되지 않도록 lower bound 0.05 적용.

---

## 3. 구현 단계

### Phase 1 — 코어 튜닝 모듈 (백엔드, 신규 파일)

**3-1. `dashboard/backend/services/backtest_objectives.py` (신규)**

목적함수·필터 계산 분리. 기존 `composite_backtest.py`에 일부 메트릭이 있다면 거기서 import.

```python
def compute_metrics(trades, equity_curve) -> dict:
    """expectancy, profit_factor, max_drawdown_pct, trade_count, win_rate"""

def passes_filter(metrics: dict) -> bool:
    """PF >= 1.5 AND MDD <= 25 AND trade_count >= 30"""
```

**3-2. `dashboard/backend/services/backtest_tuner.py` (신규)**

```python
def define_search_space(trial) -> CompositeBacktestParams:
    """Optuna trial 객체를 받아 12 파라미터 샘플링 + 가중치 정규화 + score_exit_buffer < threshold 검증"""

def run_single_window(price_data, params, window) -> dict:
    """단일 expanding window의 IS에서 best params 찾고 OOS에서 적용. composite_backtest._run_backtest_sync 재사용."""

def run_walk_forward(price_data, n_trials=200) -> list[dict]:
    """9 windows 순회. 각 window별로 Optuna study 1개 실행 → IS best → OOS 적용 → 결과 누적"""

def aggregate_results(window_results) -> dict:
    """9 windows 평균 expectancy/PF/MDD/win_rate. 필터 통과 여부 판정."""
```

**핵심 재사용 + 최소 수정:**
- `_run_backtest_sync()` 시그니처·핵심 로직(SL/TP, score_exit, flip)은 변경 금지.
- **단** `calc_tech_bullish_score()`, `calc_tech_bearish_score()`에 선택적 `weights: dict | None = None` 인자 추가 (default=None일 때 기존 단순 평균 동작 보존).
- `calc_long_score()`, `calc_short_score()`에 선택적 `macro_weight: float = 0.4` 인자 추가 (default=0.4로 기존 동작 보존).
- `CompositeBacktestParams`에 5개 가중치 필드 추가, default=None/0.4로 backwards-compat.
- 회귀 테스트로 default 호출 시 기존 결과(56.3% / -19.29%) 동일 보장.

**3-3. 의존성 추가**

`requirements.txt` 또는 `pyproject.toml`에 `optuna>=3.5.0` 추가. `pip install optuna` 1회 실행.

### Phase 2 — API 엔드포인트

**3-4. `dashboard/backend/api/sim_routes.py` 확장**

```python
@router.post("/sim/tune")
async def start_tuning(req: TuningRequest, bg: BackgroundTasks):
    """job_id 반환, BackgroundTasks로 run_walk_forward 실행"""

@router.get("/sim/tune/{job_id}")
async def get_tuning_status(job_id: str):
    """진행률 + 완료 시 상위 N개 조합 반환. backtest/results/tuning/{job_id}.json 읽기"""
```

ProcessPool은 backtest_tuner 내부에서 — n_trials 200을 ProcessPool로 parallel하게 처리.

**3-5. 결과 파일 스키마 (`backtest/results/tuning/{job_id}.json`)**

```json
{
  "job_id": "uuid",
  "status": "running|completed|failed",
  "progress": {"current_window": 5, "total_windows": 9, "current_trial": 87, "total_trials": 200},
  "started_at": "ISO8601",
  "completed_at": "ISO8601 or null",
  "config": {...},
  "windows": [
    {
      "index": 0, "is_period": "...", "oos_period": "...",
      "best_params": {...},
      "is_metrics": {...}, "oos_metrics": {...}
    }
  ],
  "aggregate": {
    "avg_oos_expectancy": 0.0023,
    "avg_oos_profit_factor": 1.62,
    "avg_oos_mdd": 18.4,
    "passes_filter": true,
    "top_combinations": [...]
  }
}
```

### Phase 3 — UI 통합

**3-6. `dashboard/frontend/src/components/shared/CompositeSimulator.tsx` 확장**

- "자동 튜닝 실행" 버튼 추가
- `POST /sim/tune` 호출 → job_id 받기 → 폴링(5초 간격)으로 `/sim/tune/{job_id}` 조회
- 진행률 표시: "Window 5/9, Trial 87/200"

**3-7. `dashboard/frontend/src/components/shared/TuningResultTable.tsx` (신규)**

- 9 windows OOS 결과 평균 + 필터 통과 여부(✅/❌) 헤더
- 상위 10개 조합 테이블: expectancy / PF / MDD / win_rate / trade_count + 12 파라미터
- 한 행 클릭 → 해당 파라미터로 단일 백테스트(`POST /sim/composite-backtest`) 재실행 → 기존 자본곡선 컴포넌트로 결과 확인

### Phase 4 — 문서

**3-8. `docs/plans/tuning-runbook.md` (신규)**
- IS vs OOS expectancy 격차 해석법
- "필터 통과 조합 0개"일 때 의미와 다음 액션
- Optuna study 결과 재현 방법

---

## 4. 핵심 파일

**수정 (default 인자로 backwards-compat 보장):**
- `dashboard/backend/services/composite_backtest.py:25` — `CompositeBacktestParams`에 5개 가중치 필드 추가
- `dashboard/backend/services/composite_backtest.py:109,179` — `calc_tech_bullish_score`/`calc_tech_bearish_score`에 `weights` 인자 추가
- `dashboard/backend/services/composite_backtest.py:243,248` — `calc_long_score`/`calc_short_score`에 `macro_weight` 인자 추가
- `dashboard/backend/services/composite_backtest.py:_run_backtest_sync` — `params`로부터 가중치 추출해 점수 함수에 전달 (핵심 로직은 무수정)
- `dashboard/backend/api/sim_routes.py` — `/sim/tune` POST/GET 엔드포인트 2개 추가, `CompositeBacktestRequest`에 5개 가중치 필드 추가(선택)
- `dashboard/frontend/src/components/shared/CompositeSimulator.tsx` — "자동 튜닝" 버튼 + 폴링 로직 추가

**신규:**
- `dashboard/backend/services/backtest_tuner.py`
- `dashboard/backend/services/backtest_objectives.py`
- `dashboard/frontend/src/components/shared/TuningResultTable.tsx`
- `backtest/results/tuning/` 디렉토리
- `docs/plans/tuning-runbook.md`

**의존성:**
- `optuna>=3.5.0` 신규 추가 (사용자 승인됨)

---

## 5. Verification (E2E)

1. **유닛 검증**: `compute_metrics()`를 합성 trades 리스트로 검증 (승 3 패 2, 평균수익/평균손실/PF/MDD 수동 계산값과 일치).
2. **단일 trial 검증**: Optuna trial 1개로 12 파라미터 샘플링 → 가중치 합 1.0 확인 → score_exit_buffer < threshold 보장 확인.
3. **단일 window 검증**: 1번째 window(IS 3개월/OOS 1개월)만 50 trials로 빠르게 돌려서 IS best → OOS 적용 흐름 확인.
4. **전체 9 windows 통합**: n_trials=200 풀 실행 (예상 30분~1시간). job 상태 폴링 정상, JSON 결과 저장 확인.
5. **회귀 검증**: 가중치 default값(weights=None, macro_weight=0.4)으로 호출 시 기존 단일 백테스트 결과(56.3% / -19.29%)가 그대로 재현되는지 — 기존 단순 평균 로직과 수치적 동등성 보장.
6. **UI 수동**: "자동 튜닝" → 진행률 표시 → 결과 테이블 → 행 클릭 → 자본곡선 정상 렌더.

### 성공 판정

```
9 windows OOS 평균이 다음을 모두 만족하는 조합이 1개 이상 존재:
  expectancy > 0 AND profit_factor ≥ 1.5 AND max_drawdown_pct ≤ 25 AND trade_count ≥ 30
```

**판정 결과별 다음 액션:**
- ✅ 통과: "꾸준히 수익 나는 베이스라인" 확보. 후속 plan에서 승률 끌어올리기 + 다른 심볼/TF 확장.
- ❌ 미통과: 신호 체계 자체의 한계 시사. 별도 plan으로 지표 재설계 또는 ML 신호 도입 검토. **이번 plan에서는 추가 튜닝 시도하지 말 것**(과적합 함정).

---

## 6. Non-goals (이번 plan 범위 밖)

- **다른 심볼/타임프레임 확장** — BTCUSDT 1h에 한정. ETH·4h·15m 등은 후속 plan
- **70% 승률 추구** — 베이스라인 수익성 확보 후 별도 plan으로 분리
- **실시간 자동매매 연결** — 시뮬레이터 전용
- **신규 지표/ML 모델 도입** — 기존 5 base + 14 booster만 사용
- **분산 워커**(Celery/Redis 등) — BackgroundTasks + ProcessPool로 충분

---

## 7. 다음 단계 (이 plan 승인 후)

CLAUDE.md 워크플로우: **ouroboros(spec) → superpowers(구현)**.

승인 후 superpowers의 `executing-plans` 또는 `subagent-driven-development` 스킬로 Phase 1 → 2 → 3 → 4 순서대로 구현 진행.
