"""9팩터 방향 복합 모델 단위 테스트."""

from __future__ import annotations

import pandas as pd

from app.macro.direction_composite import (
    FACTORS,
    build_factors,
    compute_composite,
    latest_tilt,
)

N = 300


def _series(values):
    return pd.Series(values, index=pd.date_range("2020-01-01", periods=len(values), freq="D"), dtype=float)


_RISING = _series(list(range(N)))
_FALLING = _series(list(range(N, 0, -1)))


def _aligned(bullish: bool) -> dict[str, pd.Series]:
    """bullish=True면 모든 팩터의 부호정렬 z가 +가 되도록 원시 시계열 구성."""
    d = {}
    for name, _cat, sign in FACTORS:
        if bullish:
            d[name] = _RISING if sign == +1 else _FALLING
        else:
            d[name] = _FALLING if sign == +1 else _RISING
    return d


# ── compute_composite / latest_tilt ──────────────────────────
def test_all_bullish_long():
    t = latest_tilt(_aligned(bullish=True))
    assert t.direction == "long"
    assert t.confidence > 0
    assert t.n_factors == len(FACTORS)


def test_all_bearish_short():
    t = latest_tilt(_aligned(bullish=False))
    assert t.direction == "short"
    assert t.confidence > 0


def test_flat_inputs_neutral():
    # 상수 시계열 → std 0 → z NaN → 중립, 신뢰도 0
    flat = {name: _series([5.0] * N) for name, _c, _s in FACTORS}
    t = latest_tilt(flat)
    assert t.direction == "neutral"
    assert t.confidence == 0.0


def test_insufficient_history_neutral():
    short = {name: _series(list(range(100))) for name, _c, _s in FACTORS}  # <250 워밍업
    t = latest_tilt(short)
    assert t.direction == "neutral"
    assert t.confidence == 0.0


def test_negative_sign_factor_inverts():
    # dxy_13w(-부호) 상승 → 약세여야 함 (달러 강세 → BTC 약세)
    t = latest_tilt({"dxy_13w": _RISING})
    assert t.direction == "short"
    assert t.contributions["dxy_13w"] < 0


def test_missing_factors_uses_available():
    t = latest_tilt({"vix_level": _RISING, "rsi14": _RISING})
    assert t.n_factors == 2
    assert t.direction == "long"  # 둘 다 +부호 상승


def test_direction_kr_label():
    assert latest_tilt(_aligned(bullish=True)).direction_kr == "강세"


# ── build_factors ────────────────────────────────────────────
def test_build_factors_13w_change():
    f = build_factors(
        close=_RISING, net_liquidity=_RISING, dxy=_RISING, ust10y=_RISING,
        vix=_RISING, mvrv=_RISING, active_addr=_RISING,
    )
    # 13주(91일) 변화: 마지막 = v[-1] - v[-92] = 299 - 208 = 91
    assert f["net_liquidity_13w"].iloc[-1] == 91
    assert set(f) == {n for n, _c, _s in FACTORS}  # 9개 전부


def test_build_factors_rsi_range():
    f = build_factors(
        close=_RISING, net_liquidity=_RISING, dxy=_RISING, ust10y=_RISING,
        vix=_RISING, mvrv=_RISING, active_addr=_RISING,
    )
    rsi = f["rsi14"].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_build_factors_drops_missing_source():
    f = build_factors(
        close=_RISING, net_liquidity=None, dxy=_RISING, ust10y=_RISING,
        vix=_RISING, mvrv=_RISING, active_addr=_RISING,
    )
    assert "net_liquidity_13w" not in f
    assert "dxy_13w" in f
