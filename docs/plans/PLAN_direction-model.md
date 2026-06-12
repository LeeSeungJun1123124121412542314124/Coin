# 변동성 정기 리포트 — 방향 모델 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `periodic_report`에 계층 게이트 기반 롱/숏/중립 방향 bias + 0~100 신뢰도를 산출·표기하고, 오해 유발 라벨을 사실 기반으로 리라이팅한 뒤 alert_level×방향 9칸 추천 매트릭스를 제공한다.

**Architecture:** 새 순수 모듈 `direction_model.py`(상수는 `direction_constants.py`)가 기술 1차 방향(HA + HMA/MACD 크로스)을 결정하고 파생·온체인·MVRV·F&G를 신뢰도로 가감한다. `technical_analyzer`가 방향 raw 입력을 details로 surface하고, `score_aggregator`가 4개 분석 결과를 모아 `compute_direction()`을 호출해 `AggregatedResult.direction`에 담는다. `message_formatter`가 '방향' 섹션·라벨 리라이팅·9칸 매트릭스를 렌더한다. 검증은 단위테스트 14건 + `direction_backtest.py`(기술 1차 방향 적중률 ≥55%).

**Tech Stack:** Python, pandas, PyYAML, pytest. 기존 `crypto-volatility-bot/app/analyzers`, `heikin_ashi.py`, `macd.py`, `hull_ma.py`, `app/backtest` 재사용.

**스코프 한계(명시):** 백테스트 엔진은 OHLCV(기술)만 보유하므로 **1차 기술 방향**만 백테스트로 검증한다(보조 신뢰도 4종은 과거 onchain/파생 데이터 부재로 단위테스트로만 검증). 1차 방향이 곧 롱/숏 콜이고 보조는 신뢰도(중립 강등)만 조정하므로 1차 방향 적중률이 모델의 핵심 지표다.

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `app/analyzers/direction_constants.py` | 가중치·deadband·임계값 상수 | 신규 |
| `app/analyzers/direction_model.py` | `DirectionBias` + `compute_direction()` 순수 함수 | 신규 |
| `app/analyzers/technical_analyzer.py` | `ha_direction`/`hma_cross`/`macd_cross`를 details로 surface | 수정 |
| `app/analyzers/score_aggregator.py` | `compute_direction` 호출 + `AggregatedResult.direction` 필드 | 수정 |
| `app/notifiers/message_formatter.py` | '방향' 섹션, 라벨 리라이팅, 9칸 매트릭스 | 수정 |
| `app/backtest/direction_backtest.py` | 1차 방향 슬라이딩 백테스트(hit_rate) | 신규 |
| `tests/unit/test_direction_model.py` | 모델 단위테스트 12건 | 신규 |
| `tests/unit/test_message_formatter.py` | 포매터 방향 테스트 2건 | 수정(추가) |
| `tests/unit/test_direction_backtest.py` | 백테스트 함수 smoke 1건 | 신규 |

---

## Task 1: 상수 모듈

**Files:**
- Create: `crypto-volatility-bot/app/analyzers/direction_constants.py`

- [ ] **Step 1: 상수 모듈 작성**

```python
"""방향 모델 상수 — 가중치·deadband·임계값(수동 튜닝 지점).

모든 방향/신뢰도 튜닝은 이 파일에서만 수행한다. 코드 로직 변경 불필요.
"""

from __future__ import annotations

# ── 신뢰도 점수 ───────────────────────────────────────────────
BASE_CONFIDENCE = 50.0      # 1차 방향 확정 시 출발점
CONFIRM_DELTA = 15.0        # 보조 카테고리(파생/온체인) confirm 가산
DIVERGENCE_DELTA = -15.0    # 보조 카테고리 divergence 감산
NUDGE_DELTA = 10.0          # MVRV/F&G 극단 컨트레리언 nudge 크기
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 100.0
CONFIDENCE_CUTOFF = 30.0    # 미만이면 방향 '중립' 강등

# ── deadband(무가산 0 구간) ──────────────────────────────────
FR_DEADBAND = 0.00005       # |FR| < 이 값이면 방향성 없음
FLOW_RATIO_LOW = 0.95       # flow_ratio 0.95~1.05는 방향성 없음
FLOW_RATIO_HIGH = 1.05

# ── MVRV 임계값 ──────────────────────────────────────────────
MVRV_OVERHEATED = 3.5       # 초과 시 숏 nudge
MVRV_UNDERVALUED = 0.8      # 미만 시 롱 nudge
MVRV_RISK_LOW = 2.5         # 2.5~3.5: 방향 미반영, '과열 위험' 부기

# ── F&G 임계값 ───────────────────────────────────────────────
FG_EXTREME_FEAR = 25        # 미만: 극단 공포 → 롱 nudge
FG_EXTREME_GREED = 75       # 초과: 극단 탐욕 → 숏 nudge
```

- [ ] **Step 2: 임포트 확인**

Run: `cd crypto-volatility-bot; python -c "import app.analyzers.direction_constants as c; print(c.BASE_CONFIDENCE, c.CONFIDENCE_CUTOFF)"`
Expected: `50.0 30.0`

- [ ] **Step 3: 커밋**

```bash
git add crypto-volatility-bot/app/analyzers/direction_constants.py
git commit -m "feat: 방향 모델 상수 모듈 추가"
```

---

## Task 2: 방향 모델 (TDD)

**Files:**
- Create: `crypto-volatility-bot/app/analyzers/direction_model.py`
- Test: `crypto-volatility-bot/tests/unit/test_direction_model.py`

방향 매핑 규칙(컨트레리언):
- 파생 FR: `FR < 0`(숏 쏠림) → **롱 레인**, `FR > 0`(롱 쏠림) → **숏 레인**.
- 온체인 flow_ratio: `< 1`(outflow>inflow, 매집) → **롱 레인**, `> 1` → **숏 레인**.
- MVRV: `> 3.5` → 숏 nudge, `< 0.8` → 롱 nudge.
- F&G: `< 25` → 롱 nudge, `> 75` → 숏 nudge.
- 1차 방향과 같은 레인이면 confirm(+), 반대면 divergence(−).
- 크로스 표기는 `macd.py`/`hull_ma` 관례인 `"golden"`/`"death"` 사용. 롱에 반대 = `"death"`, 숏에 반대 = `"golden"`.

- [ ] **Step 1: 실패하는 테스트 작성 (게이트 4 + 신뢰도 4 + deadband 3 + 컷오프 1 = 12건)**

`crypto-volatility-bot/tests/unit/test_direction_model.py`:

```python
"""방향 모델 단위 테스트 — compute_direction()."""

from __future__ import annotations

from app.analyzers.direction_model import compute_direction


# ── 1차 방향 게이트 (4건) ────────────────────────────────────
def test_ha_bullish_both_golden_long():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross="golden", macd_cross="golden",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "long"
    assert b.final_direction == "long"


def test_ha_bullish_both_death_downgrade_neutral():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross="death", macd_cross="death",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "neutral"
    assert b.final_direction == "neutral"


def test_ha_bearish_one_oppose_stays_short():
    # 숏에 반대 = golden. macd golden만 반대, hma death는 동조 → 둘 다 반대 아님 → 숏 유지
    b = compute_direction(
        ha_bullish=False, ha_bearish=True, hma_cross="death", macd_cross="golden",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "short"


def test_ha_bullish_one_death_stays_long():
    # 롱에 반대 = death. macd death만 반대 → 둘 다 반대 아님 → 롱 유지
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross="golden", macd_cross="death",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "long"


# ── 신뢰도 가감 (4건) ────────────────────────────────────────
def test_all_confirm_high_confidence():
    # 롱: FR<0(롱레인 confirm +15), flow<1(롱레인 confirm +15), mvrv<0.8(롱 nudge +10), fg<25(롱 nudge +10)
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=-0.001, flow_ratio=0.8, mvrv=0.5, fear_greed=10,
    )
    assert b.confidence == 100.0
    assert b.final_direction == "long"
    assert b.confirm_count == 2
    assert b.divergence_count == 0


def test_all_divergence_low_confidence():
    # 롱: FR>0(숏레인 div -15), flow>1(숏레인 div -15), mvrv>3.5(숏 nudge -10), fg>75(숏 nudge -10)
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=0.001, flow_ratio=1.5, mvrv=4.0, fear_greed=90,
    )
    assert b.confidence == 0.0
    assert b.final_direction == "neutral"
    assert b.divergence_count == 2


def test_mvrv_extreme_nudge_only():
    # 롱, mvrv>3.5 숏 nudge -10 → 40
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=None, mvrv=4.0, fear_greed=None,
    )
    assert b.confidence == 40.0
    assert b.final_direction == "long"


def test_fg_extreme_nudge_only():
    # 롱, fg<25 롱 nudge +10 → 60
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=10,
    )
    assert b.confidence == 60.0
    assert b.final_direction == "long"


# ── deadband (3건) ───────────────────────────────────────────
def test_fr_deadband_zero():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=0.00001, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.confidence == 50.0
    assert b.confirm_count == 0 and b.divergence_count == 0


def test_flow_deadband_zero():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=1.0, mvrv=None, fear_greed=None,
    )
    assert b.confidence == 50.0
    assert b.confirm_count == 0 and b.divergence_count == 0


def test_missing_inputs_zero():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.confidence == 50.0
    assert b.final_direction == "long"


# ── 컷오프 (1건) ─────────────────────────────────────────────
def test_confidence_below_cutoff_neutral():
    # 롱, FR>0 div -15, mvrv>3.5 숏 nudge -10 → 25 (<30) → 중립 강등
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=0.001, flow_ratio=None, mvrv=4.0, fear_greed=None,
    )
    assert b.confidence == 25.0
    assert b.primary_direction == "long"
    assert b.final_direction == "neutral"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_model.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analyzers.direction_model'`

- [ ] **Step 3: 모델 구현**

`crypto-volatility-bot/app/analyzers/direction_model.py`:

```python
"""방향 모델 — 계층 게이트(기술 1차) + 보조 신뢰도 가감.

기술(HA + HMA/MACD 크로스)이 1차 방향(long/short/neutral)을 결정한다.
파생·온체인은 confirm/divergence로 신뢰도를 ±15 가감, MVRV·F&G 극단은
±10 nudge. 신뢰도<30이면 방향을 '중립'으로 강등한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analyzers import direction_constants as C


@dataclass
class DirectionBias:
    primary_direction: str   # "long" | "short" | "neutral" (기술 1차)
    confidence: float        # 0~100
    final_direction: str     # "long" | "short" | "neutral" (컷오프 반영)
    confirm_count: int       # 1차 방향을 confirm한 보조 카테고리 수
    divergence_count: int    # 1차 방향에 divergence인 보조 카테고리 수
    evidence: str            # 근거 한 줄 ("파생 confirm · 온체인 divergence")


_OPPOSING_CROSS = {"long": "death", "short": "golden"}


def _primary_from_technical(
    ha_bullish: bool, ha_bearish: bool, hma_cross: str | None, macd_cross: str | None
) -> str:
    """HA 1차 방향 + 크로스 둘 다 반대면 중립 강등."""
    if ha_bullish:
        primary = "long"
    elif ha_bearish:
        primary = "short"
    else:
        return "neutral"

    opp = _OPPOSING_CROSS[primary]
    hma_opp = hma_cross == opp
    macd_opp = macd_cross == opp
    if hma_opp and macd_opp:
        return "neutral"
    return primary


def _fr_lean(funding_rate: float | None) -> str | None:
    """파생 컨트레리언 레인: FR<0 숏쏠림→롱, FR>0 롱쏠림→숏."""
    if funding_rate is None or abs(funding_rate) < C.FR_DEADBAND:
        return None
    return "long" if funding_rate < 0 else "short"


def _flow_lean(flow_ratio: float | None) -> str | None:
    """온체인 레인: flow_ratio<1 매집→롱, >1 유입우위→숏."""
    if flow_ratio is None or C.FLOW_RATIO_LOW <= flow_ratio <= C.FLOW_RATIO_HIGH:
        return None
    return "long" if flow_ratio < 1.0 else "short"


def _mvrv_lean(mvrv: float | None) -> str | None:
    """MVRV 극단만: >3.5 숏, <0.8 롱."""
    if mvrv is None:
        return None
    if mvrv > C.MVRV_OVERHEATED:
        return "short"
    if mvrv < C.MVRV_UNDERVALUED:
        return "long"
    return None


def _fg_lean(fear_greed: float | None) -> str | None:
    """F&G 극단만: <25 롱, >75 숏."""
    if fear_greed is None:
        return None
    if fear_greed < C.FG_EXTREME_FEAR:
        return "long"
    if fear_greed > C.FG_EXTREME_GREED:
        return "short"
    return None


def compute_direction(
    *,
    ha_bullish: bool,
    ha_bearish: bool,
    hma_cross: str | None,
    macd_cross: str | None,
    funding_rate: float | None,
    flow_ratio: float | None,
    mvrv: float | None,
    fear_greed: float | None,
) -> DirectionBias:
    primary = _primary_from_technical(ha_bullish, ha_bearish, hma_cross, macd_cross)

    if primary == "neutral":
        return DirectionBias(
            primary_direction="neutral",
            confidence=C.BASE_CONFIDENCE,
            final_direction="neutral",
            confirm_count=0,
            divergence_count=0,
            evidence="방향 불명확",
        )

    confidence = C.BASE_CONFIDENCE
    confirm_count = 0
    divergence_count = 0
    parts: list[str] = []

    # 보조 카테고리(파생/온체인) — confirm/divergence ±15
    for label, lean in (("파생", _fr_lean(funding_rate)), ("온체인", _flow_lean(flow_ratio))):
        if lean is None:
            continue
        if lean == primary:
            confidence += C.CONFIRM_DELTA
            confirm_count += 1
            parts.append(f"{label} confirm")
        else:
            confidence += C.DIVERGENCE_DELTA
            divergence_count += 1
            parts.append(f"{label} divergence")

    # nudge(MVRV/F&G) — ±10, confirm/divergence 카운트엔 미포함
    for label, lean in (("MVRV", _mvrv_lean(mvrv)), ("F&G", _fg_lean(fear_greed))):
        if lean is None:
            continue
        confidence += C.NUDGE_DELTA if lean == primary else -C.NUDGE_DELTA
        parts.append(f"{label} nudge")

    confidence = max(C.CONFIDENCE_MIN, min(C.CONFIDENCE_MAX, confidence))
    final = primary if confidence >= C.CONFIDENCE_CUTOFF else "neutral"
    evidence = " · ".join(parts) if parts else "보조 신호 없음"

    return DirectionBias(
        primary_direction=primary,
        confidence=confidence,
        final_direction=final,
        confirm_count=confirm_count,
        divergence_count=divergence_count,
        evidence=evidence,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_model.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/analyzers/direction_model.py crypto-volatility-bot/tests/unit/test_direction_model.py
git commit -m "feat: 방향 모델 compute_direction + 단위테스트 12건"
```

---

## Task 3: technical_analyzer가 방향 raw 입력 surface

**Files:**
- Modify: `crypto-volatility-bot/app/analyzers/technical_analyzer.py` (analyze() 끝부분 + 신규 헬퍼)
- Test: `crypto-volatility-bot/tests/unit/test_direction_model.py` (surfacing 1건 추가)

부스터 게이트(`ha_filter.enabled`)와 무관하게 항상 `ha_direction`/`hma_cross`/`macd_cross`를 details에 넣는다.

- [ ] **Step 1: 실패하는 surfacing 테스트 추가**

`tests/unit/test_direction_model.py` 하단에 추가:

```python
def test_technical_analyzer_surfaces_direction_inputs(sample_ohlcv_df):
    from app.analyzers.technical_analyzer import TechnicalAnalyzer

    result = TechnicalAnalyzer().analyze(sample_ohlcv_df)
    d = result.details
    assert d["ha_direction"] in ("bullish", "bearish", "neutral")
    assert d["hma_cross"] in ("golden", "death", None)
    assert d["macd_cross"] in ("golden", "death", None)
```

- [ ] **Step 2: 실패 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_model.py::test_technical_analyzer_surfaces_direction_inputs -q`
Expected: FAIL — `KeyError: 'ha_direction'`

- [ ] **Step 3: analyze()에 surfacing 추가**

[technical_analyzer.py](../crypto-volatility-bot/app/analyzers/technical_analyzer.py)의 `analyze()`에서 `details["signal_boost"] = boost_details` 다음 줄에 삽입:

```python
        details["base_score"] = base_score
        details["signal_boost"] = boost_details
        # 방향 모델용 raw 입력 surface (부스터 게이트와 무관하게 항상 계산)
        ha_mode = self._ha_filter_cfg.get("mode", "simple")
        details.update(self._compute_direction_inputs(df, ha_mode))
```

그리고 클래스에 신규 staticmethod 추가(`_compute_mtf_indicators` 아래 등 적절한 위치):

```python
    @staticmethod
    def _compute_direction_inputs(df: pd.DataFrame, ha_mode: str = "simple") -> dict[str, Any]:
        """방향 모델용 raw 입력: HA 캔들 방향 + HMA/MACD 크로스."""
        from app.analyzers.indicators import heikin_ashi, hull_ma, macd

        ha = heikin_ashi.calculate(df, mode=ha_mode)
        if ha["ha_bullish"]:
            ha_direction = "bullish"
        elif ha["ha_bearish"]:
            ha_direction = "bearish"
        else:
            ha_direction = "neutral"

        close = df["close"]
        mhull = hull_ma.hma(close, 30)
        shull = hull_ma.hma(close, 10)
        hma_cross: str | None = None
        if (
            len(mhull) >= 2
            and not pd.isna(mhull.iloc[-1]) and not pd.isna(shull.iloc[-1])
            and not pd.isna(mhull.iloc[-2]) and not pd.isna(shull.iloc[-2])
        ):
            pm, ps = float(mhull.iloc[-2]), float(shull.iloc[-2])
            cm, cs = float(mhull.iloc[-1]), float(shull.iloc[-1])
            if pm <= ps and cm > cs:
                hma_cross = "golden"
            elif pm >= ps and cm < cs:
                hma_cross = "death"

        macd_cross = macd.calculate(df)["crossover"]  # "golden" / "death" / None

        return {"ha_direction": ha_direction, "hma_cross": hma_cross, "macd_cross": macd_cross}
```

- [ ] **Step 4: 통과 확인 + 기존 기술 테스트 무회귀**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_model.py tests/unit/test_technical_analyzer.py -q`
Expected: PASS (전부 통과)

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/analyzers/technical_analyzer.py crypto-volatility-bot/tests/unit/test_direction_model.py
git commit -m "feat: technical_analyzer가 방향 raw 입력(ha_direction/hma_cross/macd_cross) surface"
```

---

## Task 4: score_aggregator 통합

**Files:**
- Modify: `crypto-volatility-bot/app/analyzers/score_aggregator.py`
- Test: `crypto-volatility-bot/tests/unit/test_direction_model.py` (통합 1건 추가)

- [ ] **Step 1: 실패하는 통합 테스트 추가**

`tests/unit/test_direction_model.py` 하단에 추가:

```python
def test_aggregator_attaches_direction():
    from app.analyzers.base import AnalysisResult
    from app.analyzers.score_aggregator import ScoreAggregator

    onchain = AnalysisResult(score=50, signal="NEUTRAL",
                             details={"flow_ratio": 0.8, "mvrv": 0.5, "whale_alert": False})
    technical = AnalysisResult(score=50, signal="LOW",
                               details={"ha_direction": "bullish", "hma_cross": "golden",
                                        "macd_cross": "golden"})
    sentiment = AnalysisResult(score=50, signal="NEUTRAL", details={"fear_greed_index": 10})

    agg = ScoreAggregator().aggregate(onchain, technical, sentiment, derivatives=None)
    assert agg.direction is not None
    assert agg.direction.final_direction == "long"
```

- [ ] **Step 2: 실패 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_model.py::test_aggregator_attaches_direction -q`
Expected: FAIL — `AttributeError: 'AggregatedResult' object has no attribute 'direction'`

- [ ] **Step 3: aggregator 수정**

[score_aggregator.py](../crypto-volatility-bot/app/analyzers/score_aggregator.py) 상단 임포트에 추가:

```python
from app.analyzers.direction_model import DirectionBias, compute_direction
```

`AggregatedResult` dataclass에 필드 추가(`details` 다음):

```python
    details: dict[str, Any] = field(default_factory=dict)
    direction: DirectionBias | None = None
```

`aggregate()`의 `return AggregatedResult(...)` 직전에 방향 계산 추가:

```python
        tdet = technical.details
        direction = compute_direction(
            ha_bullish=tdet.get("ha_direction") == "bullish",
            ha_bearish=tdet.get("ha_direction") == "bearish",
            hma_cross=tdet.get("hma_cross"),
            macd_cross=tdet.get("macd_cross"),
            funding_rate=(derivatives.details.get("funding_rate") if derivatives else None),
            flow_ratio=onchain.details.get("flow_ratio"),
            mvrv=onchain.details.get("mvrv"),
            fear_greed=sentiment.details.get("fear_greed_index"),
        )

        return AggregatedResult(
            final_score=score,
            alert_score=tech_score,
            alert_level=alert_level,
            whale_alert=whale_alert,
            details=details,
            direction=direction,
        )
```

- [ ] **Step 4: 통과 확인 + 무회귀**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_model.py tests/unit/ -q`
Expected: PASS (전부 통과)

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/analyzers/score_aggregator.py crypto-volatility-bot/tests/unit/test_direction_model.py
git commit -m "feat: score_aggregator가 AggregatedResult.direction에 방향 bias 부착"
```

---

## Task 5: message_formatter — 방향 섹션 + 라벨 리라이팅 + 9칸 매트릭스

**Files:**
- Modify: `crypto-volatility-bot/app/notifiers/message_formatter.py`
- Test: `crypto-volatility-bot/tests/unit/test_message_formatter.py` (2건 추가)

- [ ] **Step 1: 실패하는 포매터 테스트 2건 추가**

`tests/unit/test_message_formatter.py` 하단에 추가:

```python
def _make_result(alert_level, direction_bias):
    from datetime import datetime, timezone
    from app.analyzers.score_aggregator import AggregatedResult

    return AggregatedResult(
        final_score=70.0,
        alert_score=70.0,
        alert_level=alert_level,
        whale_alert=False,
        timestamp=datetime(2026, 6, 12, tzinfo=timezone.utc),
        details={
            "technical_score": 70.0, "onchain_score": 50.0, "sentiment_score": 50.0,
            "onchain_signal": "NEUTRAL", "sentiment_signal": "NEUTRAL",
            "derivatives_signal": "NEUTRAL", "flow_ratio": 0.8, "mvrv": 0.5,
        },
        direction=direction_bias,
    )


def test_periodic_report_renders_direction_section():
    from app.analyzers.direction_model import DirectionBias
    from app.notifiers.message_formatter import MessageFormatter

    bias = DirectionBias(primary_direction="long", confidence=65.0, final_direction="long",
                         confirm_count=1, divergence_count=1, evidence="파생 confirm · 온체인 divergence")
    out = MessageFormatter().periodic_report("BTC/USDT", _make_result("MEDIUM", bias))
    assert "방향: 롱 (신뢰도 65/100)" in out
    assert "파생 confirm · 온체인 divergence" in out


def test_recommendation_matrix_cells():
    from app.analyzers.direction_model import DirectionBias
    from app.notifiers.message_formatter import MessageFormatter

    high_short = DirectionBias("short", 70.0, "short", 2, 0, "파생 confirm")
    out_hs = MessageFormatter().periodic_report("BTC/USDT", _make_result("HIGH", high_short))
    assert "단기 숏 우위, 변동성 확대 주의" in out_hs

    low_neutral = DirectionBias("neutral", 50.0, "neutral", 0, 0, "방향 불명확")
    out_ln = MessageFormatter().periodic_report("BTC/USDT", _make_result("LOW", low_neutral))
    assert "변동성 낮음, 관망" in out_ln
```

- [ ] **Step 2: 실패 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_message_formatter.py::test_periodic_report_renders_direction_section -q`
Expected: FAIL — 방향 섹션 미출력으로 assert 실패

- [ ] **Step 3: 포매터 구현**

[message_formatter.py](../crypto-volatility-bot/app/notifiers/message_formatter.py) 상단(`_SIGNAL_EMOJI` 아래)에 매핑·헬퍼 추가:

```python
_DIRECTION_LABEL = {"long": "롱", "short": "숏", "neutral": "중립"}

# 변동성 등급 버킷 (alert_level → LOW/MID/HIGH)
_VOL_BUCKET = {
    "CONFIRMED_HIGH": "HIGH", "HIGH": "HIGH", "LIQUIDATION_RISK": "HIGH",
    "MEDIUM": "MID", "LOW": "LOW",
}

_RECO_MATRIX = {
    ("LOW", "long"): "변동성 낮음, 롱 우위(약)",
    ("LOW", "short"): "변동성 낮음, 숏 우위(약)",
    ("LOW", "neutral"): "변동성 낮음, 관망",
    ("MID", "long"): "변동성 보통, 롱 우위",
    ("MID", "short"): "변동성 보통, 숏 우위",
    ("MID", "neutral"): "변동성 보통, 방향 불명확",
    ("HIGH", "long"): "단기 롱 우위, 변동성 확대 주의",
    ("HIGH", "short"): "단기 숏 우위, 변동성 확대 주의",
    ("HIGH", "neutral"): "변동성 확대 경보, 방향 불명확 — 포지션 축소 권고",
}
_RECO_FALLBACK = {"LOW": "변동성 낮음", "MID": "변동성 보통", "HIGH": "변동성 확대 경보"}


def _direction_recommendation(alert_level: str, bias: Any, mvrv: Any) -> str:
    """alert_level × 방향 9칸 매트릭스 + <30 폴백 + MVRV 중간 과열 부기."""
    from app.analyzers import direction_constants as DC

    bucket = _VOL_BUCKET.get(str(alert_level), "MID")
    if bias is None or bias.confidence < DC.CONFIDENCE_CUTOFF:
        reco = _RECO_FALLBACK[bucket]
    else:
        reco = _RECO_MATRIX[(bucket, bias.final_direction)]

    mvrv_val = _to_float(mvrv, float("nan"))
    if mvrv_val == mvrv_val and DC.MVRV_RISK_LOW <= mvrv_val <= DC.MVRV_OVERHEATED:
        reco += " · MVRV 과열 위험"
    return reco


def _format_direction_section(bias: Any) -> list[str]:
    """신설 '방향' 섹션."""
    if bias is None:
        return []
    label = _DIRECTION_LABEL.get(bias.final_direction, "중립")
    return [
        "<b>🧭 방향</b>",
        f"방향: {label} (신뢰도 {bias.confidence:.0f}/100)",
        f"근거: {bias.evidence}",
    ]
```

`periodic_report()` 수정 — 방향 섹션 삽입 + 추천 문구를 매트릭스로 교체. 기존 마지막 줄
`lines += ["", f"💡 {_recommendation(result.alert_level)}"]` 을 다음으로 교체하고, `_format_tech_detail` 다음에 방향 섹션을 추가:

```python
        lines += _format_tech_detail(d)
        # 신설 '방향' 섹션
        direction_lines = _format_direction_section(getattr(result, "direction", None))
        if direction_lines:
            lines += [""] + direction_lines
        lines += [
            "",
            "<b>핵심 지표</b>",
            f"- 온체인: {onchain_sig} (점수 {onchain_score:.1f}, 유입/유출 비율 {flow_ratio:.2f})",
            f"- 감성: {sentiment_sig} (점수 {sentiment_score:.1f}" + (f", 공포탐욕지수 {fgi})" if fgi is not None else ")"),
            f"- 파생: OI 3일 {oi_chg:+.1f}% | FR {_fr_pct(fr)} | 시그널 {deriv_sig}",
            "",
            "<b>트리거 근거</b>",
        ]

        if base_score is not None and boost_total is not None:
            lines.append(f"- 기술 점수 = 기본 {_to_float(base_score):.1f} + 부스터 {boost_total:.1f}")
        else:
            lines.append("- 기술 점수 분해 데이터 없음")
        lines.append(f"- 활성 부스터: {booster_top3}")

        reco = _direction_recommendation(result.alert_level, getattr(result, "direction", None), d.get("mvrv"))
        lines += ["", f"💡 {reco}"]
        return "\n".join(lines)
```

> 참고: 핵심 지표의 온체인 줄은 이미 "유입/유출 비율 {flow_ratio}"로 사실 기반이라 라벨 리라이팅 충족. `_format_dashboard_summary`/`_format_tech_detail`의 표기는 사실 기반(수치)으로 유지된다. 방향 해석은 '방향' 섹션이 전담.

- [ ] **Step 4: 통과 확인 + 무회귀**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_message_formatter.py -q`
Expected: PASS (전부 통과)

- [ ] **Step 5: 커밋**

```bash
git add crypto-volatility-bot/app/notifiers/message_formatter.py crypto-volatility-bot/tests/unit/test_message_formatter.py
git commit -m "feat: periodic_report 방향 섹션 + alert_level×방향 9칸 추천 매트릭스"
```

---

## Task 6: 1차 방향 백테스트 (≥55% 검증)

**Files:**
- Create: `crypto-volatility-bot/app/backtest/direction_backtest.py`
- Test: `crypto-volatility-bot/tests/unit/test_direction_backtest.py`

기존 엔진은 onchain/파생 과거 데이터가 없으므로, 기술 1차 방향만 슬라이딩 평가하는 전용 함수를 추가(엔진 무수정, `TechnicalAnalyzer` 재사용).

- [ ] **Step 1: 실패하는 smoke 테스트 작성**

`tests/unit/test_direction_backtest.py`:

```python
"""1차 방향 백테스트 smoke 테스트."""

from __future__ import annotations

from app.backtest.direction_backtest import run_direction_backtest


def test_run_direction_backtest_smoke(high_volatility_ohlcv_df):
    # 100봉 fixture는 window+eval에 못 미쳐 빈 결과여야 함 (구조 검증용)
    res = run_direction_backtest(high_volatility_ohlcv_df, window_size=50, evaluation_bars=10)
    assert "hit_rate" in res
    assert "total_evaluated" in res
    assert 0.0 <= res["hit_rate"] <= 1.0
```

- [ ] **Step 2: 실패 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_backtest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.backtest.direction_backtest'`

- [ ] **Step 3: 백테스트 함수 구현**

`crypto-volatility-bot/app/backtest/direction_backtest.py`:

```python
"""1차 기술 방향 백테스트 — 슬라이딩 윈도우로 방향 적중률 측정.

엔진(engine.py)은 변동성 점수용. 본 모듈은 방향 모델의 기술 1차 방향만
과거 OHLCV로 평가한다(보조 신뢰도 입력은 과거 데이터 부재로 None).
"""

from __future__ import annotations

import logging

import pandas as pd

from app.analyzers.direction_model import compute_direction
from app.analyzers.technical_analyzer import TechnicalAnalyzer

logger = logging.getLogger(__name__)


def run_direction_backtest(
    df: pd.DataFrame,
    *,
    window_size: int = 100,
    evaluation_bars: int = 24,
    config_path: str | None = None,
) -> dict[str, float]:
    """방향 적중률 측정.

    Args:
        df: 전체 과거 OHLCV.
        window_size: 분석 윈도우 봉 수.
        evaluation_bars: 방향 평가 호라이즌(1h봉 기준 24=24h).

    Returns:
        {"hit_rate", "total_evaluated", "correct"} — final_direction이 neutral인
        구간은 평가 제외.
    """
    analyzer = TechnicalAnalyzer(config_path)
    n = len(df)
    correct = 0
    total = 0

    for end in range(window_size, n - evaluation_bars):
        window = df.iloc[end - window_size : end].reset_index(drop=True)
        try:
            res = analyzer.analyze(window)
        except Exception as e:  # noqa: BLE001
            logger.debug("윈도우 %d 분석 실패 (건너뜀): %s", end, e)
            continue

        d = res.details
        bias = compute_direction(
            ha_bullish=d.get("ha_direction") == "bullish",
            ha_bearish=d.get("ha_direction") == "bearish",
            hma_cross=d.get("hma_cross"),
            macd_cross=d.get("macd_cross"),
            funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
        )
        if bias.final_direction == "neutral":
            continue

        future_close = float(df.iloc[end + evaluation_bars - 1]["close"])
        current_close = float(df.iloc[end - 1]["close"])
        actual = "long" if future_close > current_close else "short"
        if actual == bias.final_direction:
            correct += 1
        total += 1

    return {
        "hit_rate": correct / total if total > 0 else 0.0,
        "total_evaluated": float(total),
        "correct": float(correct),
    }
```

- [ ] **Step 4: 통과 확인**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/test_direction_backtest.py -q`
Expected: PASS

- [ ] **Step 5: 실데이터 적중률 측정 (AC ≥55%)**

BTC/USDT 과거 OHLCV로 실측. 데이터 소스는 기존 `scripts/backtest_real_data.py` 패턴 참고(동일 collector 사용). 임시 실행:

Run:
```bash
cd crypto-volatility-bot
python -c "import pandas as pd; from app.backtest.direction_backtest import run_direction_backtest; df=pd.read_csv('<btc_1h_history.csv>'); print(run_direction_backtest(df, window_size=100, evaluation_bars=24))"
```
Expected: `hit_rate` 출력. **AC: hit_rate ≥ 0.55**. 미달 시 `direction_constants.py` 튜닝(크로스 다운그레이드 룰/컷오프) 또는 evaluation_bars 조정 후 재측정. (데이터 파일 경로는 실행자가 준비; 없으면 collector로 수집하는 1회성 스크립트 작성.)

- [ ] **Step 6: 커밋**

```bash
git add crypto-volatility-bot/app/backtest/direction_backtest.py crypto-volatility-bot/tests/unit/test_direction_backtest.py
git commit -m "feat: 1차 방향 백테스트 함수 + smoke 테스트"
```

---

## Task 7: 전체 검증 + 커버리지

- [ ] **Step 1: 전체 단위테스트 통과**

Run: `cd crypto-volatility-bot; python -m pytest tests/unit/ -q`
Expected: PASS (기존 + 신규 14건 전부)

- [ ] **Step 2: 신규 모듈 라인 커버리지 ≥90% 확인**

Run:
```bash
cd crypto-volatility-bot
python -m pytest tests/unit/test_direction_model.py tests/unit/test_message_formatter.py \
  --cov=app.analyzers.direction_model --cov=app.notifiers.message_formatter \
  --cov-report=term-missing -q
```
Expected: `direction_model.py` 라인 커버리지 ≥ 90%. (message_formatter는 방향 섹션 함수 위주 — 미달 시 매트릭스 분기 테스트 보강.)

- [ ] **Step 3: 샘플 리포트 육안 검수**

Run:
```bash
cd crypto-volatility-bot
python -c "
from datetime import datetime, timezone
from app.analyzers.direction_model import DirectionBias
from app.analyzers.score_aggregator import AggregatedResult
from app.notifiers.message_formatter import MessageFormatter
bias = DirectionBias('long', 65, 'long', 1, 1, '파생 confirm · 온체인 divergence')
r = AggregatedResult(70,70,'HIGH',False,datetime.now(timezone.utc),
  {'technical_score':70,'onchain_score':50,'sentiment_score':50,'onchain_signal':'NEUTRAL',
   'sentiment_signal':'NEUTRAL','derivatives_signal':'NEUTRAL','flow_ratio':0.8,'mvrv':2.7,
   'oi_3d_chg_pct':12.0,'funding_rate':-0.0001,'fear_greed_index':20}, bias)
print(MessageFormatter().periodic_report('BTC/USDT', r))
"
```
Expected: '🧭 방향' 섹션 + "단기 롱 우위, 변동성 확대 주의 · MVRV 과열 위험" 출력 확인.

- [ ] **Step 4: 최종 커밋(필요 시)**

```bash
git add -A
git commit -m "test: 방향 모델 전체 검증 + 커버리지 확인"
```

---

## Self-Review 체크

- **스펙 커버리지**: 계층 게이트(T2/T3) · 신뢰도 0~100+컷오프(T2) · 컨트레리언 매핑(T2) · deadband(T1/T2) · 방향 섹션(T5) · 라벨 리라이팅(T5 주석/기존 사실표기 유지) · 9칸 매트릭스(T5) · 백테스트 ≥55%(T6) · 단위테스트 14건(T2 12 + T5 2) · 스펙 문서(`docs/SPEC_direction-model.md` 기존) — 전 항목 매핑됨.
- **타입 일관성**: 크로스 표기 `"golden"`/`"death"`로 통일(`macd.py` 관례). 방향 어휘 `long`/`short`/`neutral`로 통일. `DirectionBias` 필드명 전 태스크 일관.
- **테스트 수**: 모델 12 + 포매터 2 = 14(AC) + surfacing 1 + 통합 1 + 백테스트 smoke 1 = 총 17(14는 AC 명시분).

## Execution 참고

- 권장: superpowers:subagent-driven-development (태스크당 신규 subagent + 단계 리뷰).
- 또는 superpowers:executing-plans (인라인 배치 실행 + 체크포인트).
- 커밋 단위: 태스크별 1커밋(이미 각 태스크 Step에 커밋 포함).
