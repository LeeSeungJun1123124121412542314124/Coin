"""backtest_baseline — 8년 복합 백테스트의 순수 계산부 테스트.

계획: docs/plans/spf-phase2-3-calibration-reweight-2026-07-05.md 0단계.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.macro.backtest_baseline import (
    build_history_frame,
    forward_hit_stats,
    rank_ic,
)


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2020-01-01", periods=n, freq="D")


# ── rank_ic (순위 피어슨 = 연구 문서 방법론) ─────────────────────


def test_rank_ic_perfect_monotonic_is_one() -> None:
    idx = _dates(50)
    a = pd.Series(np.arange(50, dtype=float), index=idx)
    b = a * 3 + 7  # 단조 동일 순위
    assert rank_ic(a, b) == pytest.approx(1.0)


def test_rank_ic_perfect_inverse_is_minus_one() -> None:
    idx = _dates(50)
    a = pd.Series(np.arange(50, dtype=float), index=idx)
    b = -a
    assert rank_ic(a, b) == pytest.approx(-1.0)


def test_rank_ic_ignores_nan_pairs() -> None:
    idx = _dates(52)
    a = pd.Series(np.arange(52, dtype=float), index=idx)
    b = a * 2
    a.iloc[3], b.iloc[7] = np.nan, np.nan
    # NaN 페어 제거 후에도 완전 단조 → 1.0
    assert rank_ic(a, b) == pytest.approx(1.0)


def test_rank_ic_returns_none_when_pairs_insufficient() -> None:
    idx = _dates(10)
    a = pd.Series(np.arange(10, dtype=float), index=idx)
    # 유효 페어 10 < 30 → 유의성 부족으로 None
    assert rank_ic(a, a) is None


# ── forward_hit_stats ────────────────────────────────────────────


def test_forward_hit_stats_all_long_and_rising() -> None:
    """복합 +1(강세), 가격 매일 상승 → 강세 적중 100%."""
    idx = _dates(40)
    composite = pd.Series(1.0, index=idx)
    close = pd.Series(np.linspace(100.0, 200.0, 40), index=idx)

    stats = forward_hit_stats(composite, close, horizons=(7,), neutral_band=0.15)

    h = stats["7"]
    assert h["n_long"] == 33   # 마지막 7일은 forward 미확정 → 제외
    assert h["n_short"] == 0
    assert h["n_neutral"] == 0
    assert h["hit_long"] == pytest.approx(100.0)
    assert h["hit_directional"] == pytest.approx(100.0)
    assert h["ic"] is not None


def test_forward_hit_stats_neutral_band_excluded_from_hits() -> None:
    """|z| < band 인 날은 중립 버킷으로 빠지고 적중률 계산에서 제외."""
    idx = _dates(40)
    z = np.full(40, 1.0)
    z[:10] = 0.05  # 중립 구간
    composite = pd.Series(z, index=idx)
    close = pd.Series(np.linspace(100.0, 200.0, 40), index=idx)

    stats = forward_hit_stats(composite, close, horizons=(7,), neutral_band=0.15)

    h = stats["7"]
    assert h["n_neutral"] == 10
    assert h["n_long"] == 23
    assert h["hit_long"] == pytest.approx(100.0)


def test_forward_hit_stats_short_hits_when_falling() -> None:
    """복합 -1(약세), 가격 매일 하락 → 약세 적중 100%, baseline 상승률 0%."""
    idx = _dates(30)
    composite = pd.Series(-1.0, index=idx)
    close = pd.Series(np.linspace(200.0, 100.0, 30), index=idx)

    stats = forward_hit_stats(composite, close, horizons=(7, 14), neutral_band=0.15)

    for horizon in ("7", "14"):
        h = stats[horizon]
        assert h["n_long"] == 0
        assert h["hit_short"] == pytest.approx(100.0)
        assert h["baseline_up_rate"] == pytest.approx(0.0)


def test_forward_hit_stats_mixed_directions() -> None:
    """전반 상승(강세 예측)·후반 하락(약세 예측) → 양방향 100%."""
    idx = _dates(60)
    close = pd.Series(
        np.concatenate([np.linspace(100.0, 200.0, 30), np.linspace(200.0, 100.0, 30)]),
        index=idx,
    )
    z = np.concatenate([np.full(30, 1.0), np.full(30, -1.0)])
    composite = pd.Series(z, index=idx)

    stats = forward_hit_stats(composite, close, horizons=(7,), neutral_band=0.15)

    h = stats["7"]
    # 경계(30일차 부근)는 방향이 엇갈릴 수 있어 정확 100%는 아님 — 우세 확인
    assert h["n_long"] > 0 and h["n_short"] > 0
    assert h["hit_long"] > 70.0
    assert h["hit_short"] > 70.0


# ── build_history_frame ──────────────────────────────────────────


def _synthetic_sources(n: int = 400) -> dict[str, pd.Series]:
    idx = _dates(n)
    rng = np.random.default_rng(42)
    walk = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), index=idx)
    return {
        "close": walk,
        "net_liquidity": pd.Series(np.linspace(5e6, 6e6, n), index=idx),
        "tga": pd.Series(np.linspace(4e5, 8e5, n), index=idx),
        "dxy": pd.Series(100 + np.sin(np.arange(n) / 30.0), index=idx),
        "ust10y": pd.Series(np.linspace(1.5, 4.5, n), index=idx),
        "vix": pd.Series(20 + 5 * np.cos(np.arange(n) / 20.0), index=idx),
        "mvrv": pd.Series(1.5 + 0.5 * np.sin(np.arange(n) / 50.0), index=idx),
        "active_addr": pd.Series(np.linspace(8e5, 1.1e6, n), index=idx),
    }


def test_build_history_frame_has_factors_composite_close() -> None:
    frame = build_history_frame(_synthetic_sources())

    # 9팩터 + composite + close 컬럼
    for col in (
        "net_liquidity_13w", "dxy_13w", "ust10y_13w", "vix_level", "mvrv_level",
        "active_addr_13w", "rsi14", "sma50_dist", "momentum_30d", "composite", "close",
    ):
        assert col in frame.columns, col
    # 워밍업(250일) 이후 composite 산출
    assert frame["composite"].iloc[-1] == frame["composite"].iloc[-1]  # not NaN
    assert frame["composite"].iloc[:200].isna().all()


def test_build_history_frame_roundtrips_via_csv(tmp_path) -> None:
    frame = build_history_frame(_synthetic_sources())
    path = tmp_path / "history.csv"
    frame.to_csv(path)

    loaded = pd.read_csv(path, index_col=0, parse_dates=True)

    assert list(loaded.columns) == list(frame.columns)
    pd.testing.assert_series_equal(loaded["composite"], frame["composite"], check_freq=False)
