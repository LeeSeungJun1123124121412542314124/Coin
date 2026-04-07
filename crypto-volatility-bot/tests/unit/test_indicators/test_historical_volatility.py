"""Tests for Historical Volatility indicator."""

from app.analyzers.indicators.historical_volatility import calculate


def test_hv_returns_positive_float(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=20)
    assert isinstance(result, float)
    assert result > 0


def test_hv_high_vol_greater_than_low_vol(high_volatility_ohlcv_df, low_volatility_ohlcv_df):
    high = calculate(high_volatility_ohlcv_df, period=20)
    low = calculate(low_volatility_ohlcv_df, period=20)
    assert high > low
