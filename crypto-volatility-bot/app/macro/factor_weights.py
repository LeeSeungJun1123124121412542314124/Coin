"""리더보드 스냅샷에서 SPF 복합 팩터 가중치를 산출한다."""

from __future__ import annotations

from datetime import datetime, timezone

from app.macro.direction_composite import FACTORS

_INDICATOR_FACTOR_MAP: dict[str, tuple[str, ...]] = {
    "순유동성": ("net_liquidity_13w",),
    "VIX": ("vix_level",),
    "MVRV": ("mvrv_level",),
    "긴축환경": ("dxy_13w", "ust10y_13w"),
    "과열회귀": ("rsi14",),
}


def derive_weights(leaderboard_snapshot: list[dict]) -> dict:
    """유효한 리더보드 Sharpe를 팩터별 상대 가중치로 변환한다."""
    factor_sharpes: dict[str, float] = {}
    for row in leaderboard_snapshot:
        factors = _INDICATOR_FACTOR_MAP.get(row["indicator"])
        sharpe = row["sharpe"]
        if not factors or row["n_days_equity"] < 30 or sharpe is None:
            continue
        split_sharpe = float(sharpe) / len(factors)
        for factor in factors:
            factor_sharpes[factor] = split_sharpe

    weights = {name: 1.0 for name, _category, _sign in FACTORS}
    if factor_sharpes:
        mean_sharpe = sum(factor_sharpes.values()) / len(factor_sharpes)
        if mean_sharpe != 0:
            for factor, sharpe in factor_sharpes.items():
                weights[factor] = min(2.0, max(0.5, sharpe / mean_sharpe))

    return {
        "weights": weights,
        "meta": {
            "version": "spf-phase3-v1",
            "derived_at": datetime.now(timezone.utc).isoformat(),
            "snapshot": leaderboard_snapshot,
        },
    }
