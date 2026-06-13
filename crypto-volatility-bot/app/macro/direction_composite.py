"""거시·온체인·기술 9팩터 방향 복합 모델.

검증: docs/RESEARCH_direction-signals.md (IC90 0.35, OOS TRAIN 0.38/TEST 0.35).
각 팩터를 bullish=+ 로 부호정렬 → causal 확장창 z-score → 동등가중 평균 = composite.
composite > 0 강세 / < 0 약세, |composite| → 신뢰도. 시장(BTC) 전체 방향 tilt.

기존 HA 기반 app/analyzers/direction_model.py는 데이터로 무효화됨(이 모듈이 대체).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# ── 튜닝 상수 ────────────────────────────────────────────────
_Z_MIN_PERIODS = 250        # causal z 워밍업 (일)
_NEUTRAL_BAND = 0.15        # |composite z| 이 값 미만이면 중립
_CONFIDENCE_FULL_Z = 1.0    # |composite z| 이 값이면 신뢰도 100

# 9팩터: (이름, 카테고리, bullish 부호)  부호 -1 = 값↑일수록 약세
FACTORS: list[tuple[str, str, int]] = [
    ("net_liquidity_13w", "macro", +1),     # 순유동성 13주 변화↑ → 강세
    ("dxy_13w", "macro", -1),               # 달러 13주 변화↑ → 약세
    ("ust10y_13w", "macro", -1),            # 10년물 13주 변화↑ → 약세
    ("vix_level", "macro", +1),             # VIX↑(공포) → (컨트레리언) 강세
    ("mvrv_level", "onchain", -1),          # MVRV↑(고평가) → 약세
    ("active_addr_13w", "onchain", +1),     # 활성주소 13주 변화↑ → 강세
    ("rsi14", "technical", +1),             # 일봉 RSI↑(모멘텀) → 강세
    ("sma50_dist", "technical", +1),        # SMA50 이격↑ → 강세
    ("momentum_30d", "technical", +1),      # 30일 모멘텀↑ → 강세
]

_DIRECTION_KR = {"long": "강세", "short": "약세", "neutral": "중립"}


@dataclass
class DirectionTilt:
    direction: str                       # "long" | "short" | "neutral"
    confidence: float                    # 0~100
    composite_z: float                   # 원시 복합 z
    contributions: dict[str, float] = field(default_factory=dict)  # 팩터별 부호정렬 z
    n_factors: int = 0                   # 유효 팩터 수

    @property
    def direction_kr(self) -> str:
        return _DIRECTION_KR.get(self.direction, "중립")


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def build_factors(
    *,
    close: pd.Series,
    net_liquidity: pd.Series,
    dxy: pd.Series,
    ust10y: pd.Series,
    vix: pd.Series,
    mvrv: pd.Series,
    active_addr: pd.Series,
) -> dict[str, pd.Series]:
    """원시 소스(일봉 정렬) → 9팩터 변환 시계열. 누락 소스는 결과에서 제외.

    모든 입력은 동일한 일봉 DatetimeIndex로 정렬돼 있어야 한다(ffill된 거시/온체인 포함).
    """
    def chg13(s: pd.Series | None) -> pd.Series | None:
        return None if s is None else s - s.shift(91)

    out: dict[str, pd.Series | None] = {
        "net_liquidity_13w": chg13(net_liquidity),
        "dxy_13w": chg13(dxy),
        "ust10y_13w": chg13(ust10y),
        "vix_level": vix,
        "mvrv_level": mvrv,
        "active_addr_13w": chg13(active_addr),
        "rsi14": _rsi(close) if close is not None else None,
        "sma50_dist": (close / close.rolling(50).mean() - 1) if close is not None else None,
        "momentum_30d": (close / close.shift(30) - 1) if close is not None else None,
    }
    return {k: v for k, v in out.items() if v is not None}


def _causal_z(s: pd.Series) -> pd.Series:
    """확장창 z-score (미래정보 배제)."""
    mean = s.expanding(min_periods=_Z_MIN_PERIODS).mean()
    std = s.expanding(min_periods=_Z_MIN_PERIODS).std()
    return (s - mean) / std


def compute_composite(factor_inputs: dict[str, pd.Series]) -> pd.Series:
    """팩터 변환 시계열 dict → 복합 z 시계열 (bullish 부호정렬 causal z의 동등가중 평균).

    가용 팩터만 사용(누락 무시). 입력이 전무하면 ValueError.
    """
    aligned = []
    for name, _cat, sign in FACTORS:
        s = factor_inputs.get(name)
        if s is None:
            continue
        aligned.append((_causal_z(s) * sign).rename(name))
    if not aligned:
        raise ValueError("compute_composite: 가용 팩터 없음")
    return pd.concat(aligned, axis=1).mean(axis=1, skipna=True)


def latest_tilt(factor_inputs: dict[str, pd.Series]) -> DirectionTilt:
    """최신 시점의 방향 tilt. 워밍업 미달/데이터 부족 시 중립(confidence 0)."""
    composite = compute_composite(factor_inputs)
    z = float(composite.iloc[-1]) if len(composite) else float("nan")
    if z != z:  # NaN (워밍업 미달)
        return DirectionTilt(direction="neutral", confidence=0.0, composite_z=0.0, n_factors=0)

    contributions: dict[str, float] = {}
    for name, _cat, sign in FACTORS:
        s = factor_inputs.get(name)
        if s is None:
            continue
        cz = (_causal_z(s) * sign).iloc[-1]
        if cz == cz:
            contributions[name] = round(float(cz), 2)

    if z >= _NEUTRAL_BAND:
        direction = "long"
    elif z <= -_NEUTRAL_BAND:
        direction = "short"
    else:
        direction = "neutral"
    confidence = max(0.0, min(100.0, abs(z) / _CONFIDENCE_FULL_Z * 100.0))
    return DirectionTilt(
        direction=direction,
        confidence=round(confidence, 1),
        composite_z=round(z, 3),
        contributions=contributions,
        n_factors=len(contributions),
    )
