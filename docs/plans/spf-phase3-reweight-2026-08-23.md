# SPF 3단계 — 9팩터 재가중 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 복합 방향 모델의 9팩터 동등가중을 IC 기반 가중평균으로 바꾸되, walk-forward OOS(미학습 구간) 적중률이 동등가중을 넘을 때만 채택한다.

**Architecture:** 0단계가 만든 8년 오프라인 데이터(`data/composite_sources.csv`)를 그대로 재사용한다. 가중치는 팩터별 forward rank IC에 비례해 산출하고(음수 IC 팩터는 0), 과적합 방지는 확장 윈도우 walk-forward로 한다 — 각 폴드의 학습 구간에서만 가중치를 뽑아 검증 구간 composite를 만들고, 이어붙인 OOS 시계열을 같은 구간의 동등가중과 비교한다. 순수 계산부는 `app/macro/factor_weights.py`(신규 모듈), 실행·리포트는 `scripts/reweight_factors.py`(신규 CLI)로 나눈다 — 0단계의 `backtest_baseline.py` + `composite_history.py` 구조를 그대로 따른다.

**Tech Stack:** Python 3.12 / pandas / pytest (봇 전용 venv `crypto-volatility-bot/.venv`) — **새 의존성 없음**

---

## 배경 — 원 계획서에서 바뀐 전제

원 계획 [spf-phase2-3-calibration-reweight-2026-07-05.md](spf-phase2-3-calibration-reweight-2026-07-05.md) §3단계는 **"리더보드 실측(총수익·Sharpe·승률)으로 팩터별 가중치 산출"** 이었고, 근거는 "리더보드 지표 ↔ 복합 팩터 1:1 근접"이었다.

**그 전제는 더 이상 성립하지 않는다.** 계획서 작성(07-05) 하루 전인 커밋 `f829244`(2026-07-04, "리더보드 지표 개편 — 결합 지표 3종 신설")이 달러·금리·TGA·RSI·모멘텀30d를 개별 지표에서 은퇴시키고 결합 지표로 합쳤다(`app/macro/signals.py:97-98`). 현재 레지스트리 기준 대응 관계는:

| 복합 팩터 (9) | 리더보드 대응 |
|---|---|
| `net_liquidity_13w` / `vix_level` / `mvrv_level` | 순유동성 / VIX / MVRV — **1:1** |
| `dxy_13w`, `ust10y_13w` | 긴축환경에 **합산** (분리 불가) |
| `rsi14` | 과열회귀에 **합산** (볼린저와 묶임) |
| `active_addr_13w`, `sma50_dist`, `momentum_30d` | **대응 지표 없음** |

리더보드 실측으로는 9팩터 중 3개만 직접 근거를 댈 수 있다. 따라서 **가중치 산출 근거를 8년 백테스트로 바꾸고, 리더보드는 사후 정합성 확인용으로만 쓴다.** 은퇴한 5개 포트폴리오의 DB 행(`paper_portfolios`, 2026-07-04에서 정지)은 이력 보존용이며 이 작업에서 쓰지 않는다.

**참고 — 실측이 백테스트보다 나쁘다:** `predictions` 판정 완료분 기준 방향 적중률은 7일 50.0%(18/18), 30일 35.1%(13/24)로, 동등가중 백테스트 기대치(56.5% / 61.4%)를 크게 밑돈다. 표본이 작아(30일 37건) 확정은 못 하지만, **재가중이 이 괴리를 자동으로 메워주지는 않는다.** Task 4의 판정 게이트에서 이 점을 감안해 채택 여부를 결정한다.

## 범위

3단계(재가중)만. 2단계(확률 보정)는 계획서가 순서를 고정한 이유대로 **가중치가 확정된 뒤** 별도 계획으로 진행한다.

---

## File Structure

| 파일 | 역할 | 변경 |
|---|---|---|
| `crypto-volatility-bot/app/macro/direction_composite.py` | 팩터 정의·복합 계산. 가중치 상수와 가중평균 헬퍼가 여기 산다 | 수정 (Task 1, 5) |
| `crypto-volatility-bot/app/macro/factor_weights.py` | **신규.** IC 가중치 산출 + walk-forward OOS 순수 계산부 | 생성 (Task 2, 3) |
| `crypto-volatility-bot/scripts/reweight_factors.py` | **신규.** CSV 읽어 OOS 비교 리포트 + 전체구간 가중치 산출 → JSON | 생성 (Task 4) |
| `crypto-volatility-bot/data/composite_weights.json` | **신규(산출물).** 가중치와 그 근거 기록 | Task 4가 생성 |
| `crypto-volatility-bot/tests/unit/test_direction_composite.py` | 기존 복합 계산 테스트 | 수정 (Task 1, 5) |
| `crypto-volatility-bot/tests/unit/test_factor_weights.py` | **신규.** 가중치 산출·walk-forward 테스트 | 생성 (Task 2, 3) |

**작업 디렉터리 주의:** 봇 코드는 저장소 하위 디렉터리 `crypto-volatility-bot/`에 있지만 **별도 repo가 아니다** — git은 `E:\Dev\coin` 하나뿐이다. 반면 **pytest는 반드시 `crypto-volatility-bot/` 안에서** 돌려야 `app...` 임포트가 된다.

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit -q
```

시스템 Python이나 대시보드용 실행 경로를 쓰면 안 된다(봇 venv에만 pandas 계열이 맞춰져 있음).

---

### Task 1: 가중평균 헬퍼 도입 (동작 무변경)

가중치를 넣기 전에, **모든 가중치가 같으면 현재 동등가중과 완전히 동일한 결과**가 나오는 헬퍼를 먼저 만든다. 이게 이후 모든 비교의 기준선이 된다.

**Files:**
- Modify: `crypto-volatility-bot/app/macro/direction_composite.py`
- Test: `crypto-volatility-bot/tests/unit/test_direction_composite.py`

- [ ] **Step 1: 등가성 테스트 작성 (실패 확인용)**

`tests/unit/test_direction_composite.py` 끝에 추가한다:

```python
def test_weighted_mean_equals_plain_mean_when_weights_equal():
    """모든 가중치가 같으면 skipna 평균과 완전히 동일해야 한다.

    재가중 전후 비교의 기준선 — 이 등가성이 깨지면 개선 폭을 해석할 수 없다.
    """
    import pandas as pd
    from app.macro.direction_composite import _weighted_mean

    frame = pd.DataFrame({
        "a": [1.0, 2.0, float("nan"), 4.0],
        "b": [3.0, float("nan"), float("nan"), 0.0],
        "c": [2.0, 4.0, 6.0, float("nan")],
    })
    got = _weighted_mean(frame, {"a": 1.0, "b": 1.0, "c": 1.0})
    expected = frame.mean(axis=1, skipna=True)
    pd.testing.assert_series_equal(got, expected, check_names=False)


def test_weighted_mean_renormalizes_on_missing_factor():
    """결측 팩터가 있는 날은 가용 팩터 가중치만으로 재정규화한다."""
    import pandas as pd
    from app.macro.direction_composite import _weighted_mean

    frame = pd.DataFrame({"a": [1.0, 1.0], "b": [3.0, float("nan")]})
    got = _weighted_mean(frame, {"a": 0.25, "b": 0.75})
    # 1행: 0.25*1 + 0.75*3 = 2.5 / 1.0 = 2.5
    # 2행: b 결측 → 0.25*1 / 0.25 = 1.0
    assert list(got) == [2.5, 1.0]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit/test_direction_composite.py -q -k weighted_mean
```

Expected: FAIL — `ImportError: cannot import name '_weighted_mean'`

- [ ] **Step 3: 헬퍼와 가중치 상수 추가**

`app/macro/direction_composite.py`의 `FACTORS` 리스트 **바로 아래**에 추가한다:

```python
# 팩터 가중치 — 3단계 재가중 전 기본값은 전부 1.0(= 동등가중과 동일)
# 산출 근거: data/composite_weights.json (scripts/reweight_factors.py)
FACTOR_WEIGHTS: dict[str, float] = {name: 1.0 for name, _cat, _sign in FACTORS}
```

그리고 `compute_composite` **바로 위**에 헬퍼를 추가한다:

```python
def _weighted_mean(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """가중평균 — 결측 팩터가 있는 날은 가용 팩터 가중치만으로 재정규화.

    모든 가중치가 같으면 frame.mean(axis=1, skipna=True)와 동일하다.
    """
    w = pd.Series({c: weights.get(c, 0.0) for c in frame.columns}, dtype="float64")
    denom = frame.notna().mul(w, axis=1).sum(axis=1).where(lambda s: s > 0)
    return frame.mul(w, axis=1).sum(axis=1, min_count=1) / denom
```

- [ ] **Step 4: `compute_composite`를 헬퍼로 교체**

변경 전:
```python
    if not aligned:
        raise ValueError("compute_composite: 가용 팩터 없음")
    return pd.concat(aligned, axis=1).mean(axis=1, skipna=True)
```

변경 후:
```python
    if not aligned:
        raise ValueError("compute_composite: 가용 팩터 없음")
    return _weighted_mean(pd.concat(aligned, axis=1), FACTOR_WEIGHTS)
```

- [ ] **Step 5: 전체 테스트 통과 확인 (동작 무변경 회귀)**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit -q
```

Expected: 기존 테스트가 **하나도 깨지지 않고** 통과 + 신규 2건 통과. 기존 테스트가 하나라도 실패하면 헬퍼가 동등가중과 다르게 동작한다는 뜻이므로 멈추고 원인부터 확인한다.

- [ ] **Step 6: 베이스라인 재현 확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe scripts/composite_history.py --from-csv data/composite_sources.csv
```

Expected: 출력된 방향적중이 `data/composite_baseline.json`과 동일 — 7일 56.5 / 14일 58.6 / 30일 61.4 / 60일 64.5. **한 자리라도 다르면 Step 3~4가 동작을 바꾼 것이므로 멈춘다.**

- [ ] **Step 7: 커밋**

```bash
git add crypto-volatility-bot/app/macro/direction_composite.py crypto-volatility-bot/tests/unit/test_direction_composite.py
git commit -m "refactor: 복합 계산을 가중평균 헬퍼로 전환 (가중치 전부 1.0 — 동작 무변경)"
```

---

### Task 2: 팩터별 IC 가중치 산출

**Files:**
- Create: `crypto-volatility-bot/app/macro/factor_weights.py`
- Test: `crypto-volatility-bot/tests/unit/test_factor_weights.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_factor_weights.py`를 새로 만든다:

```python
"""3단계 재가중 — IC 기반 가중치 산출 테스트."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.macro.factor_weights import aligned_factor_z, ic_weights


def _series(values, start="2020-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_ic_weights_gives_more_weight_to_stronger_factor():
    """forward 수익과 상관이 높은 팩터가 더 큰 가중치를 받아야 한다."""
    n = 400
    rng = np.random.default_rng(0)
    fwd_driver = pd.Series(rng.normal(size=n))
    # good: 미래 수익과 강한 상관 / bad: 무관한 잡음
    z = pd.DataFrame({
        "good": fwd_driver.values,
        "bad": rng.normal(size=n),
    }, index=pd.date_range("2020-01-01", periods=n, freq="D"))
    close = pd.Series(100 * np.exp(np.cumsum(np.r_[0, fwd_driver.values[:-1]] * 0.01)), index=z.index)

    weights, ics = ic_weights(z, close, horizon=1)

    assert weights["good"] > weights["bad"]
    assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0
    assert ics["good"] > ics["bad"]


def test_ic_weights_zeroes_negative_ic_factor():
    """IC가 음수인 팩터는 가중치 0 (부호는 FACTORS에서 이미 정렬됨)."""
    n = 400
    rng = np.random.default_rng(1)
    driver = pd.Series(rng.normal(size=n))
    z = pd.DataFrame({
        "good": driver.values,
        "inverted": -driver.values,   # 미래 수익과 반대로 움직임
    }, index=pd.date_range("2020-01-01", periods=n, freq="D"))
    close = pd.Series(100 * np.exp(np.cumsum(np.r_[0, driver.values[:-1]] * 0.01)), index=z.index)

    weights, ics = ic_weights(z, close, horizon=1)

    assert weights["inverted"] == 0.0
    assert weights["good"] == 1.0
    assert ics["inverted"] < 0


def test_ic_weights_raises_when_no_positive_factor():
    """모든 팩터의 IC가 0 이하면 가중치를 정할 수 없다 — 조용히 균등분배하지 않는다."""
    n = 400
    rng = np.random.default_rng(2)
    driver = pd.Series(rng.normal(size=n))
    z = pd.DataFrame({"inverted": -driver.values},
                     index=pd.date_range("2020-01-01", periods=n, freq="D"))
    close = pd.Series(100 * np.exp(np.cumsum(np.r_[0, driver.values[:-1]] * 0.01)), index=z.index)

    with pytest.raises(ValueError, match="양의 IC"):
        ic_weights(z, close, horizon=1)


def test_aligned_factor_z_applies_sign_and_skips_missing():
    """FACTORS의 부호 정렬을 적용하고, 없는 팩터는 열에서 빠진다."""
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rising = pd.Series(np.arange(n, dtype="float64"), index=idx)
    frame = aligned_factor_z({"net_liquidity_13w": rising, "dxy_13w": rising})

    assert list(frame.columns) == ["net_liquidity_13w", "dxy_13w"]
    # 같은 입력인데 부호가 반대(net_liquidity +1, dxy -1)
    tail = frame.dropna().iloc[-1]
    assert tail["net_liquidity_13w"] == pytest.approx(-tail["dxy_13w"])
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit/test_factor_weights.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.macro.factor_weights'`

- [ ] **Step 3: 모듈 작성**

`app/macro/factor_weights.py`를 새로 만든다:

```python
"""3단계 재가중 — 팩터별 IC 가중치 산출과 walk-forward 검증.

계획: docs/plans/spf-phase3-reweight-2026-08-23.md
0단계(backtest_baseline)와 같은 오프라인 데이터를 쓰고, 같은 rank IC 정의를 재사용한다.
"""

from __future__ import annotations

import pandas as pd

from app.macro.backtest_baseline import rank_ic
from app.macro.direction_composite import FACTORS, _causal_z, _weighted_mean


def aligned_factor_z(factors: dict[str, pd.Series]) -> pd.DataFrame:
    """팩터 변환 시계열 → bullish 부호정렬 causal z 프레임 (compute_composite와 동일 전처리)."""
    cols: dict[str, pd.Series] = {}
    for name, _cat, sign in FACTORS:
        s = factors.get(name)
        if s is None:
            continue
        cols[name] = _causal_z(s) * sign
    if not cols:
        raise ValueError("aligned_factor_z: 가용 팩터 없음")
    return pd.DataFrame(cols)


def ic_weights(
    z_frame: pd.DataFrame,
    close: pd.Series,
    horizon: int = 30,
) -> tuple[dict[str, float], dict[str, float]]:
    """팩터별 forward rank IC에 비례한 가중치.

    음수·산출불가 IC는 0으로 눌러 제외하고, 남은 양의 IC를 합 1로 정규화한다.
    (IC 비례 = 계획서가 요구한 '단순 방식 우선' — 릿지 회귀는 소표본 과적합 위험)

    Returns:
        (가중치 dict, 원시 IC dict)
    """
    fwd = close.shift(-horizon) / close - 1
    ics = {name: (rank_ic(z_frame[name], fwd) or 0.0) for name in z_frame.columns}
    positive = {name: max(v, 0.0) for name, v in ics.items()}
    total = sum(positive.values())
    if total <= 0:
        raise ValueError("ic_weights: 양의 IC 팩터가 없어 가중치를 정할 수 없음")
    return {name: v / total for name, v in positive.items()}, ics


def weighted_composite(z_frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """부호정렬 z 프레임 + 가중치 → 복합 z (compute_composite와 동일 규칙)."""
    return _weighted_mean(z_frame, weights)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit/test_factor_weights.py -q
```

Expected: PASS (`4 passed`)

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/macro/factor_weights.py crypto-volatility-bot/tests/unit/test_factor_weights.py
git commit -m "feat: 팩터별 IC 비례 가중치 산출 모듈 추가"
```

---

### Task 3: walk-forward OOS 검증

가중치를 전체 구간에서 뽑아 같은 구간으로 평가하면 반드시 좋아 보인다. 학습에 쓰지 않은 구간에서만 평가해야 채택 여부를 판단할 수 있다.

**Files:**
- Modify: `crypto-volatility-bot/app/macro/factor_weights.py`
- Test: `crypto-volatility-bot/tests/unit/test_factor_weights.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/unit/test_factor_weights.py` 끝에 추가한다:

```python
def test_walk_forward_returns_oos_only_and_does_not_peek():
    """OOS 시계열은 첫 학습구간 뒤부터 시작하고, 폴드별 가중치가 기록돼야 한다."""
    from app.macro.factor_weights import walk_forward_oos_composite

    n = 1600
    rng = np.random.default_rng(3)
    driver = pd.Series(rng.normal(size=n))
    idx = pd.date_range("2018-01-01", periods=n, freq="D")
    factors = {
        "net_liquidity_13w": pd.Series(np.cumsum(driver.values), index=idx),
        "dxy_13w": pd.Series(rng.normal(size=n).cumsum(), index=idx),
    }
    close = pd.Series(100 * np.exp(np.cumsum(driver.values * 0.01)), index=idx)

    oos, folds = walk_forward_oos_composite(factors, close, horizon=30, n_folds=3, min_train=800)

    assert len(folds) == 3
    assert oos.index.is_monotonic_increasing
    assert not oos.index.has_duplicates
    # 첫 학습구간(800일) 안쪽 날짜는 OOS에 포함되면 안 된다
    assert oos.index[0] >= idx[800]
    for f in folds:
        assert pytest.approx(sum(f["weights"].values()), abs=1e-9) == 1.0


def test_walk_forward_rejects_short_sample():
    """표본이 학습구간에도 못 미치면 조용히 진행하지 않는다."""
    from app.macro.factor_weights import walk_forward_oos_composite

    idx = pd.date_range("2020-01-01", periods=100, freq="D")
    factors = {"net_liquidity_13w": pd.Series(np.arange(100, dtype="float64"), index=idx)}
    close = pd.Series(np.linspace(100, 110, 100), index=idx)

    with pytest.raises(ValueError, match="표본 부족"):
        walk_forward_oos_composite(factors, close, horizon=30, n_folds=3, min_train=800)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit/test_factor_weights.py -q -k walk_forward
```

Expected: FAIL — `ImportError: cannot import name 'walk_forward_oos_composite'`

- [ ] **Step 3: 구현**

`app/macro/factor_weights.py` 끝에 추가한다:

```python
def walk_forward_oos_composite(
    factors: dict[str, pd.Series],
    close: pd.Series,
    horizon: int = 30,
    n_folds: int = 4,
    min_train: int = 1000,
) -> tuple[pd.Series, list[dict]]:
    """확장 윈도우 walk-forward — 학습구간 IC로 가중치를 뽑아 검증구간 composite를 만든다.

    학습 라벨(forward 수익)이 검증구간을 넘겨보지 않도록 학습 끝을 horizon만큼 잘라낸다.

    Returns:
        (이어붙인 OOS 복합 z, 폴드별 기록)
    """
    z_frame = aligned_factor_z(factors)
    idx = z_frame.index[z_frame.notna().any(axis=1)]
    if len(idx) <= min_train + n_folds:
        raise ValueError(f"walk_forward_oos_composite: 표본 부족 ({len(idx)}일)")

    step = (len(idx) - min_train) / n_folds
    bounds = [min_train + round(step * k) for k in range(n_folds + 1)]

    pieces: list[pd.Series] = []
    folds: list[dict] = []
    for k in range(n_folds):
        train_end, valid_end = bounds[k], bounds[k + 1]
        # 라벨 누출 방지 — 학습 끝에서 horizon만큼 뒤로 물림
        train_idx = idx[: max(train_end - horizon, 1)]
        valid_idx = idx[train_end:valid_end]
        if not len(valid_idx):
            continue
        weights, ics = ic_weights(z_frame.loc[train_idx], close.loc[train_idx], horizon=horizon)
        pieces.append(weighted_composite(z_frame.loc[valid_idx], weights))
        folds.append({
            "fold": k + 1,
            "train": f"{idx[0].date()} ~ {train_idx[-1].date()}",
            "valid": f"{valid_idx[0].date()} ~ {valid_idx[-1].date()}",
            "weights": {n: round(v, 4) for n, v in weights.items()},
            "ic": {n: (round(v, 4) if v else 0.0) for n, v in ics.items()},
        })
    return pd.concat(pieces), folds
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit/test_factor_weights.py -q
```

Expected: PASS (`6 passed`)

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/macro/factor_weights.py crypto-volatility-bot/tests/unit/test_factor_weights.py
git commit -m "feat: walk-forward OOS 복합 시계열 산출 — 학습 라벨 누출 차단"
```

---

### Task 4: 비교 리포트 스크립트 + 판정 자료 생성

**Files:**
- Create: `crypto-volatility-bot/scripts/reweight_factors.py`
- Output: `crypto-volatility-bot/data/composite_weights.json`

- [ ] **Step 1: 스크립트 작성**

`scripts/reweight_factors.py`를 새로 만든다. `composite_history.py`의 CSV 로더와 출력 형식을 그대로 따른다:

```python
"""SPF 3단계 — 팩터 재가중 산출·비교 리포트.

사용: python scripts/reweight_factors.py --from-csv data/composite_sources.csv

동등가중 대비 walk-forward OOS 적중률을 비교하고, 전체구간 가중치를 JSON으로 남긴다.
채택 여부는 사람이 판단한다 (계획서 Task 5 게이트).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.macro.backtest_baseline import forward_hit_stats  # noqa: E402
from app.macro.direction_composite import build_factors  # noqa: E402
from app.macro.factor_weights import (  # noqa: E402
    aligned_factor_z,
    ic_weights,
    walk_forward_oos_composite,
    weighted_composite,
)
from scripts.composite_history import load_sources_csv  # noqa: E402

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_HORIZON = 30          # 가중치 산출 기준 호라이즌 (IC가 가장 높은 30일)
_N_FOLDS = 4
_MIN_TRAIN = 1000      # 약 2.7년


def _print_table(title: str, stats: dict) -> None:
    print(f"\n[{title}]")
    print(f"{'H':>4} {'강세n':>6} {'약세n':>6} {'중립n':>6} {'방향적중':>8} {'기준상승률':>10} {'IC':>7}")
    for horizon, h in stats.items():
        hit = h["hit_directional"] if h["hit_directional"] is not None else "-"
        ic = h["ic"] if h["ic"] is not None else "-"
        print(f"{horizon:>4} {h['n_long']:>6} {h['n_short']:>6} {h['n_neutral']:>6}"
              f" {hit:>8} {h['baseline_up_rate']:>10} {ic:>7}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SPF 3단계 팩터 재가중")
    parser.add_argument("--from-csv", required=True, help="0단계가 저장한 sources CSV")
    args = parser.parse_args()

    sources = load_sources_csv(args.from_csv)
    factors = build_factors(**sources)
    close = sources["close"]
    z_frame = aligned_factor_z(factors)

    # 1) walk-forward OOS 비교 — 같은 구간의 동등가중과 맞대결
    oos, folds = walk_forward_oos_composite(
        factors, close, horizon=_HORIZON, n_folds=_N_FOLDS, min_train=_MIN_TRAIN
    )
    equal = weighted_composite(z_frame, {c: 1.0 for c in z_frame.columns}).loc[oos.index]

    equal_stats = forward_hit_stats(equal, close.loc[oos.index])
    oos_stats = forward_hit_stats(oos, close.loc[oos.index])

    print(f"OOS 구간: {oos.index[0].date()} ~ {oos.index[-1].date()} ({len(oos)}일, {_N_FOLDS}폴드)")
    _print_table("동등가중 (같은 OOS 구간)", equal_stats)
    _print_table("IC 재가중 (walk-forward OOS)", oos_stats)

    print("\n[폴드별 가중치]")
    for f in folds:
        print(f"  fold{f['fold']} 검증 {f['valid']}: {f['weights']}")

    # 2) 채택 시 쓸 전체구간 가중치
    full_weights, full_ics = ic_weights(z_frame, close, horizon=_HORIZON)

    print("\n[전체구간 가중치 — 채택 시 FACTOR_WEIGHTS에 반영할 값]")
    for name, w in sorted(full_weights.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<20} {w:.4f}   (IC {full_ics[name]:+.4f})")

    report = {
        "generated_for": "SPF 3단계 — IC 비례 재가중 (docs/plans/spf-phase3-reweight-2026-08-23.md)",
        "horizon": _HORIZON,
        "n_folds": _N_FOLDS,
        "min_train": _MIN_TRAIN,
        "oos_span": f"{oos.index[0].date()} ~ {oos.index[-1].date()}",
        "oos_rows": len(oos),
        "equal_weight_oos": equal_stats,
        "reweighted_oos": oos_stats,
        "folds": folds,
        "full_span_weights": {n: round(v, 4) for n, v in full_weights.items()},
        "full_span_ic": {n: round(v, 4) for n, v in full_ics.items()},
    }
    os.makedirs(_DATA_DIR, exist_ok=True)
    path = os.path.join(_DATA_DIR, "composite_weights.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n리포트 저장: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe scripts/reweight_factors.py --from-csv data/composite_sources.csv
```

Expected: OOS 구간·두 개의 적중률 표·폴드별 가중치·전체구간 가중치가 출력되고 `data/composite_weights.json`이 생성된다. 오류 없이 끝나야 한다.

- [ ] **Step 3: 커밋**

```bash
git add crypto-volatility-bot/scripts/reweight_factors.py crypto-volatility-bot/data/composite_weights.json
git commit -m "feat: 3단계 재가중 비교 리포트 스크립트 + 산출물"
```

- [ ] **Step 4: 결과 보고**

여기서 **멈추고** 다음을 보고한다 — 채택 여부는 사람이 판단한다:
- OOS 구간과 일수
- 동등가중 OOS 방향적중 vs 재가중 OOS 방향적중 (7/14/30/60 전부)
- 중립 카운트(`n_neutral`) 변화 — 가중치가 쏠리면 분산이 커져 중립밴드 통과 빈도가 달라진다. 적중률만 보고 판단하면 안 된다.
- 폴드별 가중치가 폴드마다 크게 흔들리는지 (흔들리면 과적합 신호)

---

### Task 5: 채택 게이트 — 조건부 진행

**계획서 AC:** *"재가중 모델의 백테스트 7/14/30/60 적중률이 동등가중 이상"*

- [ ] **Step 1: 판정**

Task 4 Step 4의 수치로 판단한다.

**채택하지 않는 경우 (OOS 개선 없음 / 폴드별 가중치 불안정):**
Task 5를 진행하지 않는다. `FACTOR_WEIGHTS`는 전부 1.0인 채로 남기고, `data/composite_weights.json`과 판정 근거를 문서에 기록한 뒤 종료한다. **이것도 유효한 결과다** — 동등가중이 이미 충분하다는 증거이고, 계획서가 요구한 가드가 제대로 작동한 것이다. 이 경우 아래 Step 2~5는 건너뛴다.

**채택하는 경우:** Step 2로 진행.

- [ ] **Step 2: 회귀 테스트 먼저 작성**

`tests/unit/test_direction_composite.py`에 추가한다 (`<산출값>`은 Task 4가 출력한 전체구간 가중치로 채운다):

```python
def test_factor_weights_sum_to_one_and_cover_all_factors():
    """가중치는 합 1이고 FACTORS를 모두 덮어야 한다 (누락 팩터가 조용히 0이 되면 안 됨)."""
    from app.macro.direction_composite import FACTORS, FACTOR_WEIGHTS

    assert set(FACTOR_WEIGHTS) == {name for name, _c, _s in FACTORS}
    assert sum(FACTOR_WEIGHTS.values()) == pytest.approx(1.0)
```

- [ ] **Step 3: 가중치 반영**

`app/macro/direction_composite.py`의 `FACTOR_WEIGHTS`를 Task 4가 산출한 전체구간 값으로 교체하고, 버전 상수를 추가한다:

```python
# 복합 모델 버전 — 재가중은 forward 실측 검증을 리셋한다.
# v1(동등가중) 기간의 적중률과 v2 이후를 섞어서 평가하지 말 것.
COMPOSITE_VERSION = "v2-ic-2026-08-23"

# 팩터 가중치 — 8년 백테스트 30일 forward rank IC 비례 (walk-forward OOS 검증 통과)
# 산출 근거·OOS 비교: data/composite_weights.json
FACTOR_WEIGHTS: dict[str, float] = {
    # Task 4가 출력한 전체구간 가중치를 여기에 그대로 적는다
}
```

- [ ] **Step 4: 전체 테스트 + 베이스라인 재확인**

```bash
cd crypto-volatility-bot
./.venv/Scripts/python.exe -m pytest tests/unit -q
./.venv/Scripts/python.exe scripts/composite_history.py --from-csv data/composite_sources.csv
```

Expected: 테스트 전부 통과. `composite_history.py` 출력은 이제 **재가중 모델 기준**이라 베이스라인 JSON(56.5/58.6/61.4/64.5)과 달라지는 게 정상이다 — 다만 30일 적중률이 61.4보다 **낮아지면** 채택 판단과 모순이므로 멈추고 보고한다.

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/macro/direction_composite.py crypto-volatility-bot/tests/unit/test_direction_composite.py
git commit -m "feat: 복합 9팩터 IC 비례 재가중 적용 (v2) — walk-forward OOS 검증 통과"
```

---

## 제약 (전 태스크 공통)

- 한국어 주석 · TDD(실패 테스트 먼저) · 외과적 변경(요청 외 인접 코드 손대지 않기)
- **새 패키지 설치 금지** — pandas/numpy/pytest만 사용
- 요청 범위 이상의 추상화·설정 옵션·방어 코드 추가 금지
- 커밋 메시지는 `type: 한국어 설명` + 본문 마지막 줄에 `Co-Authored-By` 트레일러
- `git add`는 명시된 경로만 (저장소 루트에 untracked 파일들이 있으므로 `git add .` 금지)
- **`git push` 금지** — 배포 시점은 사용자가 정한다
- 리더보드·SPF 라우트·알림 파이프라인은 건드리지 않는다 (이번 범위는 복합 계산부와 오프라인 스크립트뿐)

## Non-Goals

- 2단계 확률 보정(`confidence`·`up_prob` 매핑) — 가중치 확정 후 별도 계획
- 리더보드 지표 레지스트리 변경, 은퇴 포트폴리오 정리
- `predictions` 테이블에 모델 버전 컬럼 추가 (버전은 코드 상수로만 기록)
- 실측(forward) 적중률이 백테스트에 못 미치는 원인 규명 — 별도 조사

## Self-Review

- **범위 커버리지:** 계획서 3단계 작업 1(가중치 산출) → Task 2·4, 작업 2(compute_composite 가중평균) → Task 1·5, 작업 3(전후 비교 가드) → Task 3·4·5 게이트, 작업 4(버전 태깅) → Task 5 Step 3. AC 3개(적중률 우위 / 근거 문서화 / 과적합 방지 장치)는 각각 Task 5 게이트, `composite_weights.json`, walk-forward + IC 비례(단순 방식)로 대응.
- **플레이스홀더:** Task 5 Step 3의 가중치 값만 비워뒀다 — Task 4의 실행 결과라 사전에 알 수 없고, 채우는 방법을 명시했다.
- **이름 일관성:** `aligned_factor_z`, `ic_weights`, `weighted_composite`, `walk_forward_oos_composite`, `_weighted_mean`, `FACTOR_WEIGHTS`, `COMPOSITE_VERSION` — 전 태스크에서 동일하게 사용.
