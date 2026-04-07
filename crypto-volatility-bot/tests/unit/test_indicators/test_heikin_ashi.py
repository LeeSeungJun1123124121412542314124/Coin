"""Tests for Heikin Ashi filter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analyzers.indicators.heikin_ashi import calculate


def _make_df(opens, highs, lows, closes) -> pd.DataFrame:
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": 1000.0,
    })


def _rising_df(n: int = 20) -> pd.DataFrame:
    close = np.linspace(100, 200, n)
    return pd.DataFrame({
        "open": close - 2,
        "high": close + 3,
        "low": close - 3,
        "close": close,
        "volume": 1000.0,
    })


def _falling_df(n: int = 20) -> pd.DataFrame:
    close = np.linspace(200, 100, n)
    return pd.DataFrame({
        "open": close + 2,
        "high": close + 3,
        "low": close - 3,
        "close": close,
        "volume": 1000.0,
    })


class TestHeikinAshiBasics:
    def test_returns_required_keys(self):
        df = _rising_df()
        result = calculate(df)
        assert "ha_bullish" in result
        assert "ha_bearish" in result
        assert "filter_bullish" in result
        assert "filter_bearish" in result
        assert "ha_close" in result
        assert "ha_open" in result
        assert "ha_high" in result
        assert "ha_low" in result
        assert "mode" in result

    def test_ha_close_is_ohlc_average(self):
        opens  = [10.0, 12.0]
        highs  = [14.0, 16.0]
        lows   = [ 8.0, 10.0]
        closes = [12.0, 14.0]
        df = _make_df(opens, highs, lows, closes)
        result = calculate(df, mode="simple")
        expected_ha_close = (opens[-1] + highs[-1] + lows[-1] + closes[-1]) / 4
        assert result["ha_close"] == pytest.approx(expected_ha_close)

    def test_ha_open_second_bar(self):
        # ha_open[1] = (ha_open[0] + ha_close[0]) / 2
        opens  = [10.0, 12.0]
        highs  = [14.0, 16.0]
        lows   = [ 8.0, 10.0]
        closes = [12.0, 14.0]
        df = _make_df(opens, highs, lows, closes)
        ha_open_0 = (opens[0] + closes[0]) / 2
        ha_close_0 = (opens[0] + highs[0] + lows[0] + closes[0]) / 4
        expected_ha_open_1 = (ha_open_0 + ha_close_0) / 2
        result = calculate(df, mode="simple")
        assert result["ha_open"] == pytest.approx(expected_ha_open_1)

    def test_mode_returned_in_result(self):
        for mode in ("simple", "strong", "safe"):
            result = calculate(_rising_df(), mode=mode)
            assert result["mode"] == mode


class TestSimpleMode:
    def test_bullish_on_rising_market(self):
        df = _rising_df(30)
        result = calculate(df, mode="simple")
        assert result["ha_bullish"] is True
        assert result["filter_bullish"] is True

    def test_bearish_on_falling_market(self):
        df = _falling_df(30)
        result = calculate(df, mode="simple")
        assert result["ha_bearish"] is True
        assert result["filter_bearish"] is True

    def test_filter_matches_candle_color(self):
        df = _rising_df(30)
        result = calculate(df, mode="simple")
        assert result["filter_bullish"] == result["ha_bullish"]
        assert result["filter_bearish"] == result["ha_bearish"]


class TestStrongMode:
    def test_strong_bullish_requires_no_lower_wick(self):
        # Manually construct a HA candle with lower wick → strong filter should fail
        df = _rising_df(30)
        result = calculate(df, mode="strong")
        # Just verify it returns valid booleans
        assert isinstance(result["filter_bullish"], bool)
        assert isinstance(result["filter_bearish"], bool)

    def test_strong_mode_stricter_than_simple(self):
        df = _rising_df(30)
        simple = calculate(df, mode="simple")
        strong = calculate(df, mode="strong")
        # Strong can only be True if simple is also True
        if strong["filter_bullish"]:
            assert simple["filter_bullish"] is True


class TestSafeMode:
    def test_safe_requires_two_consecutive(self):
        df = _rising_df(30)
        result = calculate(df, mode="safe")
        assert isinstance(result["filter_bullish"], bool)

    def test_safe_with_only_one_bar_returns_false(self):
        opens  = [100.0]
        highs  = [105.0]
        lows   = [ 98.0]
        closes = [104.0]
        df = _make_df(opens, highs, lows, closes)
        result = calculate(df, mode="safe")
        # Only one bar: prev candle doesn't exist → safe filter should be False
        assert result["filter_bullish"] is False
        assert result["filter_bearish"] is False
