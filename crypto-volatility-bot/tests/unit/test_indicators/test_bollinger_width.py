"""Tests for Bollinger Band Width indicator."""

from app.analyzers.indicators.bollinger_width import calculate


def test_bollinger_width_returns_positive_float(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=20)
    assert isinstance(result, float)
    assert result > 0


def test_bollinger_width_high_vol_larger(high_volatility_ohlcv_df, low_volatility_ohlcv_df):
    high = calculate(high_volatility_ohlcv_df, period=20)
    low = calculate(low_volatility_ohlcv_df, period=20)
    assert high > low
