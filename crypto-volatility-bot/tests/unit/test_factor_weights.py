"""SPF 3단계 팩터 가중치 산출 테스트."""

from __future__ import annotations

from app.macro.factor_weights import derive_weights


def _row(indicator: str, sharpe: float | None, n_days: int = 30) -> dict:
    return {"indicator": indicator, "sharpe": sharpe, "n_days_equity": n_days}


def test_derive_weights_normalizes_mapped_sharpes():
    result = derive_weights([_row("순유동성", 1.0), _row("VIX", 2.0)])

    assert result["weights"]["net_liquidity_13w"] == 2 / 3
    assert result["weights"]["vix_level"] == 4 / 3
    assert result["meta"]["snapshot"] == [
        _row("순유동성", 1.0),
        _row("VIX", 2.0),
    ]
    assert result["meta"]["version"]
    assert result["meta"]["derived_at"]


def test_derive_weights_guards_short_history_and_none_sharpe():
    result = derive_weights([
        _row("순유동성", 9.0, n_days=29),
        _row("VIX", None),
        _row("MVRV", 1.0),
    ])

    assert result["weights"]["net_liquidity_13w"] == 1.0
    assert result["weights"]["vix_level"] == 1.0
    assert result["weights"]["mvrv_level"] == 1.0


def test_derive_weights_clips_to_cap():
    result = derive_weights([
        _row("순유동성", 0.1),
        _row("VIX", 0.1),
        _row("MVRV", 10.0),
    ])

    assert result["weights"]["net_liquidity_13w"] == 0.5
    assert result["weights"]["mvrv_level"] == 2.0


def test_derive_weights_splits_combined_indicator_equally():
    result = derive_weights([_row("긴축환경", 2.0), _row("순유동성", 1.0)])

    assert result["weights"]["dxy_13w"] == 1.0
    assert result["weights"]["ust10y_13w"] == 1.0
    assert result["weights"]["net_liquidity_13w"] == 1.0


def test_derive_weights_leaves_unmapped_factors_at_one():
    result = derive_weights([_row("볼린저밴드", 5.0), _row("순유동성", 1.0)])

    assert result["weights"]["active_addr_13w"] == 1.0
    assert result["weights"]["sma50_dist"] == 1.0
    assert result["weights"]["momentum_30d"] == 1.0
