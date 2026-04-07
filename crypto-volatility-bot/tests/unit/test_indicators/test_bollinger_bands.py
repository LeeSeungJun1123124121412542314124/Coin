"""Tests for Bollinger Bands indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.analyzers.indicators.bollinger_bands import calculate


def test_bb_returns_dict_with_required_keys(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=20)
    assert isinstance(result, dict)
    for key in (
        "upper", "middle", "lower", "bandwidth", "percent_b",
        "squeeze", "expanding", "price_above_middle", "middle_line_break",
    ):
        assert key in result


def test_bb_band_ordering(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=20)
    assert result["upper"] > result["middle"] > result["lower"]


def test_bb_percent_b_range(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=20)
    assert -1.0 <= result["percent_b"] <= 2.0


def test_bb_flat_market_percent_b():
    """Flat market: close == middle, %B ~ 0.5."""
    n = 50
    close = np.ones(n) * 100.0
    df = pd.DataFrame(
        {
            "open": close, "high": close + 0.01, "low": close - 0.01,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df, period=20)
    assert abs(result["percent_b"] - 0.5) < 0.1


def test_bb_squeeze_detection():
    """Detect squeeze when bandwidth contracts significantly."""
    n = 80
    rng = np.random.default_rng(42)
    close_volatile = 100 + np.cumsum(rng.normal(0, 5, 40))
    close_flat = np.ones(40) * close_volatile[-1] + rng.normal(0, 0.1, 40)
    close = np.concatenate([close_volatile, close_flat])
    high = close + abs(rng.normal(0, 1, n))
    low = close - abs(rng.normal(0, 1, n))
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": np.ones(n)}
    )
    result = calculate(df, period=20)
    assert result["squeeze"] is True


def test_bb_middle_line_break():
    """Middle line break should be properly detected."""
    n = 50
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame(
        {
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df, period=20)
    assert result["middle_line_break"] in ("above", "below", None)


def test_bb_high_vol_wider_bandwidth(high_volatility_ohlcv_df, low_volatility_ohlcv_df):
    high = calculate(high_volatility_ohlcv_df, period=20)
    low = calculate(low_volatility_ohlcv_df, period=20)
    assert high["bandwidth"] > low["bandwidth"]
