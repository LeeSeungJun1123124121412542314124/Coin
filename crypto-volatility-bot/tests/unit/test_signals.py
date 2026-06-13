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
    assert set(sig) == set(INDICATORS)  # 10개 지표 전부


def test_macro_is_asset_common():
    """매크로/온체인 지표는 자산 공통(동일 z)."""
    sig = latest_signals(_sources())
    for ind in ("순유동성", "달러", "금리", "VIX", "MVRV", "복합방향"):
        vals = list(sig[ind].values())
        assert len(set(vals)) == 1, f"{ind}는 자산 공통이어야 함: {sig[ind]}"


def test_technical_is_per_asset():
    """기술 지표는 자산별로 산출(키 존재)."""
    sig = latest_signals(_sources())
    for ind in ("RSI", "모멘텀30d"):
        assert {"BTC", "ETH", "SOL"} <= set(sig[ind])


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
