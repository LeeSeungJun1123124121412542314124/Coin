"""지표 레지스트리 — 각 지표가 (asset) → 방향 신호(causal z) 산출.

매크로/온체인 = 시장 공통(asset 무시), 기술 = 자산별, 도미넌스 = BTC vs 알트
상대강도 로테이션, 매수보유 = 벤치마크(항상 롱).
확장: SignalFn 함수 1개 작성 + INDICATORS 등록 1줄.

스펙: docs/SPEC_paper-trading-leaderboard.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from app.macro.direction_composite import FACTORS, _causal_z, _rsi, build_factors, compute_composite

ASSETS = ["BTC", "ETH", "SOL"]
BENCHMARK = "매수보유"
_SIGN = {name: sign for name, _cat, sign in FACTORS}  # 팩터별 bullish 부호


@dataclass
class SignalContext:
    closes: dict[str, pd.Series]   # asset → 일봉 종가
    macro_z: dict[str, pd.Series]  # 팩터 → bullish 부호정렬 causal z
    composite: pd.Series           # 9팩터 복합 z


SignalFn = Callable[[SignalContext, str], pd.Series]


def build_context(sources: dict[str, pd.Series]) -> SignalContext:
    """수집 소스 → 신호 산출용 컨텍스트(공통 매크로 z·복합·자산별 종가 1회 계산)."""
    closes = {"BTC": sources["close"]}
    if sources.get("eth_close") is not None:
        closes["ETH"] = sources["eth_close"]
    if sources.get("sol_close") is not None:
        closes["SOL"] = sources["sol_close"]
    factors = build_factors(**sources)
    macro_z = {k: _causal_z(v) * _SIGN.get(k, 1) for k, v in factors.items()}
    return SignalContext(closes=closes, macro_z=macro_z, composite=compute_composite(factors))


# ── 신호 함수 (SignalFn) ─────────────────────────────────────
def _macro(factor: str) -> SignalFn:
    """매크로/온체인 = 시장 공통 (asset 무시)."""
    return lambda ctx, asset: ctx.macro_z[factor]


def _rsi_sig(ctx: SignalContext, asset: str) -> pd.Series:
    return _causal_z(_rsi(ctx.closes[asset]))


def _momentum_sig(ctx: SignalContext, asset: str) -> pd.Series:
    c = ctx.closes[asset]
    return _causal_z(c / c.shift(30) - 1)


def _bollinger_sig(ctx: SignalContext, asset: str) -> pd.Series:
    """볼린저밴드 평균회귀 — 상단(+2σ) 근접 시 숏, 하단(−2σ) 근접 시 롱 (횡보장 대응).

    signal = -(종가−SMA20)/(2σ). 부호=방향, 크기=밴드 이탈 정도. 추세장에선 역행(리더보드가 판정).
    """
    c = ctx.closes[asset]
    sma = c.rolling(20).mean()
    denom = (2 * c.rolling(20).std()).where(lambda s: s > 0)  # σ=0 → NaN(제외)
    return -((c - sma) / denom)


def _dominance_sig(ctx: SignalContext, asset: str) -> pd.Series:
    """BTC vs 알트 30일 상대강도 → BTC 우위면 BTC 롱·알트 숏 (도미넌스 로테이션)."""
    def ret(c: pd.Series) -> pd.Series:
        return c / c.shift(30) - 1
    btc = ret(ctx.closes["BTC"])
    alts = [ret(ctx.closes[a]) for a in ("ETH", "SOL") if a in ctx.closes]
    if not alts:
        return pd.Series(0.0, index=btc.index)
    dom = _causal_z(btc - pd.concat(alts, axis=1).mean(axis=1))
    return dom if asset == "BTC" else -dom


def _buyhold_sig(ctx: SignalContext, asset: str) -> pd.Series:
    """벤치마크 — 항상 롱(엔진서 1배 특례)."""
    return pd.Series(1.0, index=ctx.closes[asset].index)


INDICATORS: dict[str, SignalFn] = {
    "복합방향": lambda ctx, asset: ctx.composite,
    "순유동성": _macro("net_liquidity_13w"),
    "달러": _macro("dxy_13w"),
    "금리": _macro("ust10y_13w"),
    "VIX": _macro("vix_level"),
    "MVRV": _macro("mvrv_level"),
    "RSI": _rsi_sig,
    "모멘텀30d": _momentum_sig,
    "볼린저밴드": _bollinger_sig,
    "도미넌스": _dominance_sig,
    BENCHMARK: _buyhold_sig,
    # 새 지표 추가 = SignalFn 1개 + 여기 1줄
}


def latest_signals(sources: dict[str, pd.Series]) -> dict[str, dict[str, float]]:
    """{지표: {자산: 최신 신호 z}}. 워밍업 미달/결측 자산은 제외."""
    ctx = build_context(sources)
    out: dict[str, dict[str, float]] = {}
    for name, fn in INDICATORS.items():
        per_asset: dict[str, float] = {}
        for asset in ctx.closes:
            series = fn(ctx, asset)
            v = series.iloc[-1] if len(series) else float("nan")
            if v == v:  # NaN 제외
                per_asset[asset] = round(float(v), 3)
        out[name] = per_asset
    return out
