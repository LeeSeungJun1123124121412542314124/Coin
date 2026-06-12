"""1차 방향 백테스트 smoke 테스트."""

from __future__ import annotations

from app.backtest.direction_backtest import run_direction_backtest


def test_run_direction_backtest_smoke(high_volatility_ohlcv_df):
    res = run_direction_backtest(high_volatility_ohlcv_df, window_size=50, evaluation_bars=10)
    assert "hit_rate" in res
    assert "total_evaluated" in res
    assert 0.0 <= res["hit_rate"] <= 1.0
