"""Tests for ADX indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.analyzers.indicators.adx import calculate


def test_adx_returns_dict_with_required_keys(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=14)
    assert isinstance(result, dict)
    for key in ("adx", "plus_di", "minus_di", "adx_declining", "di_crossover"):
        assert key in result


def test_adx_in_range(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=14)
    assert 0.0 <= result["adx"] <= 100.0
    assert 0.0 <= result["plus_di"] <= 100.0
    assert 0.0 <= result["minus_di"] <= 100.0


def test_adx_trending_higher_than_flat():
    rng = np.random.default_rng(0)
    n = 80
    # Strong uptrend
    close_trend = np.linspace(100, 300, n) + rng.normal(0, 0.5, n)
    trending_df = pd.DataFrame(
        {
            "open": close_trend,
            "high": close_trend + 2.0,
            "low": close_trend - 2.0,
            "close": close_trend,
            "volume": np.ones(n),
        }
    )
    # Flat market
    close_flat = np.ones(n) * 100.0 + rng.normal(0, 0.1, n)
    flat_df = pd.DataFrame(
        {
            "open": close_flat,
            "high": close_flat + 0.5,
            "low": close_flat - 0.5,
            "close": close_flat,
            "volume": np.ones(n),
        }
    )
    assert calculate(trending_df)["adx"] > calculate(flat_df)["adx"]


def test_adx_declining_detection():
    """ADX should be declining in a market that loses its trend."""
    n = 80
    rng = np.random.default_rng(1)
    # Strong trend then goes flat
    close = np.concatenate([
        np.linspace(100, 200, 40),
        np.ones(40) * 200 + rng.normal(0, 0.5, 40),
    ])
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.ones(n),
        }
    )
    result = calculate(df, period=14)
    assert result["adx_declining"] is True


def test_adx_di_crossover_bearish():
    """Bearish DI crossover when price reverses from up to down."""
    n = 80
    close = np.concatenate([np.linspace(100, 200, 40), np.linspace(200, 100, 40)])
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": np.ones(n),
        }
    )
    result = calculate(df, period=14)
    assert result["minus_di"] > result["plus_di"] or result["di_crossover"] == "bearish"
