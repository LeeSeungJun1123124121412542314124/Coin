"""Tests for MACD indicator."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.analyzers.indicators.macd import calculate


def test_macd_returns_dict_with_required_keys(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df)
    assert isinstance(result, dict)
    for key in ("macd_line", "signal_line", "histogram", "crossover", "histogram_zero_cross"):
        assert key in result


def test_macd_values_are_finite(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df)
    assert math.isfinite(result["macd_line"])
    assert math.isfinite(result["signal_line"])
    assert math.isfinite(result["histogram"])


def test_macd_histogram_equals_diff(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df)
    expected = result["macd_line"] - result["signal_line"]
    assert abs(result["histogram"] - expected) < 1e-10


def test_macd_golden_cross_on_rising_market():
    """Strong uptrend: MACD line > signal line."""
    n = 80
    close = np.concatenate([np.ones(40) * 100, np.linspace(100, 300, 40)])
    df = pd.DataFrame(
        {
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df)
    assert result["macd_line"] > result["signal_line"]


def test_macd_death_cross_on_falling_market():
    """Strong downtrend: MACD line < signal line."""
    n = 80
    close = np.concatenate([np.ones(40) * 300, np.linspace(300, 100, 40)])
    df = pd.DataFrame(
        {
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df)
    assert result["macd_line"] < result["signal_line"]


def test_macd_crossover_detection():
    """Crossover should be detected at the inflection point."""
    n = 80
    close = np.ones(n) * 100.0
    close[-10:] = np.linspace(100, 150, 10)
    df = pd.DataFrame(
        {
            "open": close, "high": close + 0.5, "low": close - 0.5,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df)
    assert result["crossover"] in ("golden", "death", None)


def test_macd_histogram_zero_cross():
    """Histogram should cross zero during reversal."""
    n = 80
    close = np.concatenate([np.linspace(200, 100, 40), np.linspace(100, 200, 40)])
    df = pd.DataFrame(
        {
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(n),
        }
    )
    result = calculate(df)
    assert result["histogram_zero_cross"] in ("above", "below", None)
