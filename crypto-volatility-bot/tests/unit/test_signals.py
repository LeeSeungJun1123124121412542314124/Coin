"""지표 레지스트리(signals.py) 단위테스트 — 합성 데이터, 네트워크 없음."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.macro import signals
from app.macro.signals import INDICATORS, build_context, latest_signals


def _sources(n: int = 400) -> dict[str, pd.Series]:  # 13주차분(91)+min_periods(250)=341 필요
    idx = pd.date_range("2020-01-01", periods=n, freq="D")

    def s(arr) -> pd.Series:
        return pd.Series(np.asarray(arr, dtype=float), index=idx)

    t = np.arange(n)
    # 선형은 차분 분산이 0이라 causal z가 NaN → 모든 계열에 진동 성분 부여
    return {
        "close": s(100 + t + 10 * np.sin(t / 7)),          # BTC 우상향+진동
        "eth_close": s(50 + 0.5 * t + 8 * np.cos(t / 9)),  # ETH 다른 궤적
        "sol_close": s(20 + 5 * np.cos(t / 5)),            # SOL 진동
        "net_liquidity": s(1e6 + 50 * t + 5e3 * np.sin(t / 15)),
        "dxy": s(100 + 5 * np.sin(t / 12)),
        "ust10y": s(3 + 0.5 * np.sin(t / 20)),
        "vix": s(15 + 5 * np.sin(t / 10)),
        "mvrv": s(1.5 + 0.5 * np.sin(t / 25)),
        "active_addr": s(1e5 + 3e3 * np.sin(t / 18)),
    }


def test_context_has_three_assets():
    ctx = build_context(_sources())
    assert set(ctx.closes) == {"BTC", "ETH", "SOL"}
    assert len(ctx.composite) == 400


def test_latest_signals_has_all_indicators():
    sig = latest_signals(_sources())
    assert set(sig) == set(INDICATORS)  # 등록된 지표 전부


def test_registry_composition():
    """개편 확정 구성 — 표시 9개 + 매수보유(벤치마크). 달러·금리·TGA·모멘텀30d·RSI는 은퇴."""
    assert set(INDICATORS) == {
        "복합방향", "순유동성", "VIX", "MVRV", "볼린저밴드", "도미넌스",
        "유동성", "긴축환경", "과열회귀", "매수보유",
    }


def test_macro_is_asset_common():
    """매크로/온체인 지표는 자산 공통(동일 z). 매크로 멤버만 결합한 지표도 동일."""
    sig = latest_signals(_sources())
    for ind in ("순유동성", "VIX", "MVRV", "복합방향", "유동성", "긴축환경"):
        vals = list(sig[ind].values())
        assert len(set(vals)) == 1, f"{ind}는 자산 공통이어야 함: {sig[ind]}"


def test_technical_is_per_asset():
    """기술 지표는 자산별로 산출(키 존재)."""
    sig = latest_signals(_sources())
    for ind in ("볼린저밴드", "과열회귀"):
        assert {"BTC", "ETH", "SOL"} <= set(sig[ind])


def test_bollinger_mean_reversion_sign():
    """볼밴 평균회귀: 상단 이탈→숏(음수), 하단 이탈→롱(양수)."""
    from app.macro.signals import SignalContext, _bollinger_sig
    idx = pd.date_range("2024-01-01", periods=40, freq="D")
    empty = pd.Series(dtype=float)
    up = SignalContext(closes={"BTC": pd.Series([100.0] * 39 + [130.0], index=idx)}, macro_z={}, composite=empty)
    assert _bollinger_sig(up, "BTC").iloc[-1] < 0       # 급등 → 숏
    down = SignalContext(closes={"BTC": pd.Series([100.0] * 39 + [70.0], index=idx)}, macro_z={}, composite=empty)
    assert _bollinger_sig(down, "BTC").iloc[-1] > 0      # 급락 → 롱


def test_tga_sign_negated():
    """TGA 지표: tga_13w z 부호 반전(TGA↑=유동성 흡수=약세, 음수)."""
    from app.macro.signals import SignalContext, _tga_sig
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    z = pd.Series([0.0, 0.0, 0.0, 0.0, 2.0], index=idx)  # tga_13w z = +2
    ctx = SignalContext(closes={"BTC": pd.Series(range(5), index=idx, dtype=float)},
                        macro_z={"tga_13w": z}, composite=pd.Series(dtype=float))
    assert _tga_sig(ctx, "BTC").iloc[-1] == -2.0


def test_tga_missing_source_excluded():
    """tga 소스 결측 시 NaN 시리즈 → latest_signals에서 자연 제외(크래시 없음)."""
    from app.macro.signals import SignalContext, _tga_sig
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    ctx = SignalContext(closes={"BTC": pd.Series(range(5), index=idx, dtype=float)},
                        macro_z={}, composite=pd.Series(dtype=float))
    assert _tga_sig(ctx, "BTC").isna().all()


def test_combined_liquidity_is_member_mean():
    """유동성 = (순유동성z + TGA신호)/2 — TGA는 이미 부호 반전된 신호를 평균(이중 반전 금지)."""
    from app.macro.signals import SignalContext
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    ctx = SignalContext(
        closes={"BTC": pd.Series(range(5), index=idx, dtype=float)},
        macro_z={"net_liquidity_13w": pd.Series([1.0] * 5, index=idx),
                 "tga_13w": pd.Series([2.0] * 5, index=idx)},
        composite=pd.Series(dtype=float),
    )
    # TGA 신호 = -2 → (1 + (-2)) / 2 = -0.5
    assert INDICATORS["유동성"](ctx, "BTC").iloc[-1] == -0.5


def test_combined_tightening_is_member_mean():
    """긴축환경 = (달러z + 금리z)/2."""
    from app.macro.signals import SignalContext
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    ctx = SignalContext(
        closes={"BTC": pd.Series(range(5), index=idx, dtype=float)},
        macro_z={"dxy_13w": pd.Series([1.0] * 5, index=idx),
                 "ust10y_13w": pd.Series([3.0] * 5, index=idx)},
        composite=pd.Series(dtype=float),
    )
    assert INDICATORS["긴축환경"](ctx, "BTC").iloc[-1] == 2.0


def test_combined_overheat_is_member_mean():
    """과열회귀 = (RSI신호 + 볼밴신호)/2 — 자산별."""
    from app.macro.signals import _bollinger_sig, _rsi_sig
    ctx = build_context(_sources())
    for asset in ("BTC", "ETH"):
        expected = (_rsi_sig(ctx, asset).iloc[-1] + _bollinger_sig(ctx, asset).iloc[-1]) / 2
        assert abs(INDICATORS["과열회귀"](ctx, asset).iloc[-1] - expected) < 1e-12


def test_combined_partial_nan_uses_valid_members():
    """멤버 일부 NaN → 유효 멤버만 부분평균, 전 멤버 NaN → NaN."""
    from app.macro.signals import SignalContext
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    # tga 소스 결측(macro_z에 없음) → TGA 신호 전부 NaN → 순유동성만으로 부분평균
    partial = SignalContext(
        closes={"BTC": pd.Series(range(5), index=idx, dtype=float)},
        macro_z={"net_liquidity_13w": pd.Series([1.0] * 5, index=idx)},
        composite=pd.Series(dtype=float),
    )
    assert INDICATORS["유동성"](partial, "BTC").iloc[-1] == 1.0
    # 전 멤버 NaN → NaN
    all_nan = SignalContext(
        closes={"BTC": pd.Series(range(5), index=idx, dtype=float)},
        macro_z={"net_liquidity_13w": pd.Series(float("nan"), index=idx)},
        composite=pd.Series(dtype=float),
    )
    assert INDICATORS["유동성"](all_nan, "BTC").isna().all()


def test_dominance_btc_opposite_to_alts():
    """도미넌스: BTC = -ETH = -SOL (로테이션)."""
    sig = latest_signals(_sources())
    dom = sig["도미넌스"]
    assert dom["ETH"] == dom["SOL"]
    assert dom["BTC"] == -dom["ETH"]


def test_buyhold_always_long():
    sig = latest_signals(_sources())
    assert sig["매수보유"] == {"BTC": 1.0, "ETH": 1.0, "SOL": 1.0}


def test_registry_is_extensible():
    """SignalFn 1개 + 등록 1줄로 지표 추가 가능."""
    n0 = len(INDICATORS)
    INDICATORS["테스트지표"] = lambda ctx, asset: ctx.composite
    try:
        sig = latest_signals(_sources())
        assert len(INDICATORS) == n0 + 1
        assert "테스트지표" in sig
    finally:
        del INDICATORS["테스트지표"]
