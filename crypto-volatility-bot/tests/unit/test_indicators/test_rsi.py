"""Tests for RSI indicator (Wilder's smoothing + divergence)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analyzers.indicators.rsi import calculate, _find_local_peaks, _find_local_valleys


def test_rsi_returns_dict_with_required_keys(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=14)
    assert isinstance(result, dict)
    for key in ("rsi", "overbought", "oversold", "divergence", "divergence_detail", "divergence_magnitude"):
        assert key in result


def test_rsi_in_range(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=14)
    assert 0.0 <= result["rsi"] <= 100.0


def test_rsi_overbought_on_rising_market():
    n = 80
    close = np.linspace(100, 400, n)
    df = pd.DataFrame(
        {
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df, period=14)
    assert result["rsi"] > 70.0
    assert result["overbought"] is True


def test_rsi_oversold_on_falling_market():
    n = 80
    close = np.linspace(400, 100, n)
    df = pd.DataFrame(
        {
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df, period=14)
    assert result["rsi"] < 30.0
    assert result["oversold"] is True


def test_rsi_flat_market():
    n = 80
    close = np.ones(n) * 100.0
    df = pd.DataFrame(
        {
            "open": close, "high": close + 0.01, "low": close - 0.01,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df, period=14)
    assert 0.0 <= result["rsi"] <= 100.0


def test_find_local_peaks():
    data = pd.Series([1, 2, 3, 2, 1, 2, 5, 2, 1, 2, 4, 2, 1])
    peaks = _find_local_peaks(data, order=2)
    assert 6 in peaks  # value 5 is a clear peak


def test_find_local_valleys():
    data = pd.Series([5, 4, 3, 4, 5, 4, 1, 4, 5, 4, 2, 4, 5])
    valleys = _find_local_valleys(data, order=2)
    assert 6 in valleys  # value 1 is a clear valley


def test_rsi_no_divergence_on_normal_data(sample_ohlcv_df):
    """Random walk data should run without crash; divergence may or may not be detected."""
    result = calculate(sample_ohlcv_df, period=14, divergence_lookback=60)
    assert result["divergence"] is None or result["divergence"] in ("bearish", "bullish")


# ── Phase 1 new tests ─────────────────────────────────────────────────────────

def test_divergence_magnitude_is_float(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=14)
    assert isinstance(result["divergence_magnitude"], float)


def test_divergence_magnitude_zero_when_no_divergence():
    """When no divergence detected, magnitude should be 0."""
    n = 80
    close = np.ones(n) * 100.0
    df = pd.DataFrame({
        "open": close, "high": close + 0.01, "low": close - 0.01,
        "close": close, "volume": np.ones(n),
    })
    result = calculate(df, period=14)
    if result["divergence"] is None:
        assert result["divergence_magnitude"] == 0.0


def test_divergence_order_param_changes_detection():
    """Different divergence_order values should not crash and return valid results."""
    n = 100
    rng = np.random.default_rng(123)
    close = 100 + np.cumsum(rng.normal(0, 5, n))
    df = pd.DataFrame({
        "open": close, "high": close + 2, "low": close - 2,
        "close": close, "volume": np.ones(n),
    })
    for order in (2, 5, 10):
        result = calculate(df, period=14, divergence_order=order, min_peak_distance=3)
        assert result["divergence"] in (None, "bearish", "bullish")
        assert result["divergence_magnitude"] >= 0.0


def test_min_peak_distance_enforced():
    """min_peak_distance parameter accepted without error."""
    n = 100
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 3, n))
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.ones(n),
    })
    result = calculate(df, period=14, divergence_order=3, min_peak_distance=15, min_divergence_pct=0.5)
    assert isinstance(result["divergence"], (str, type(None)))


def test_min_divergence_pct_high_suppresses_divergence():
    """Very high min_divergence_pct should suppress divergence for low-volatility data."""
    n = 80
    close = 100 + np.cumsum(np.random.default_rng(99).normal(0, 0.1, n))
    df = pd.DataFrame({
        "open": close, "high": close + 0.05, "low": close - 0.05,
        "close": close, "volume": np.ones(n),
    })
    result = calculate(df, period=14, min_divergence_pct=50.0)
    assert result["divergence"] is None or result["divergence_magnitude"] >= 50.0
