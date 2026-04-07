"""Tests for ATR indicator."""

from app.analyzers.indicators.atr import calculate


def test_atr_returns_positive_float(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=14)
    assert isinstance(result, float)
    assert result > 0


def test_atr_high_vol_greater_than_low_vol(high_volatility_ohlcv_df, low_volatility_ohlcv_df):
    high = calculate(high_volatility_ohlcv_df, period=14)
    low = calculate(low_volatility_ohlcv_df, period=14)
    assert high > low
