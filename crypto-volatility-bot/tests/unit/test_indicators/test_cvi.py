"""Tests for Chaikin Volatility Index indicator."""

from app.analyzers.indicators.cvi import calculate


def test_cvi_returns_float(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=10)
    assert isinstance(result, float)


def test_cvi_returns_finite_float(sample_ohlcv_df):
    # CVI measures rate of change of HL range — sign varies; just check bounded
    result = calculate(sample_ohlcv_df, period=10)
    assert -500 < result < 500
