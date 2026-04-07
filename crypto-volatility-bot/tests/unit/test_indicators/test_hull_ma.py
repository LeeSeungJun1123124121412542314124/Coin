"""Tests for Hull Moving Average (HMA)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analyzers.indicators.hull_ma import hma, _wma


def _make_series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


class TestWMA:
    def test_wma_single_element_window(self):
        s = _make_series([1.0, 2.0, 3.0])
        result = _wma(s, 1)
        assert result.dropna().tolist() == pytest.approx([1.0, 2.0, 3.0])

    def test_wma_weights_sum_to_one(self):
        # WMA with period=3: weights [1,2,3], total=6
        # For [1,1,1] → WMA = (1+2+3)/6 = 1.0
        s = _make_series([1.0] * 10)
        result = _wma(s, 3)
        assert float(result.iloc[-1]) == pytest.approx(1.0)

    def test_wma_last_value_has_higher_weight(self):
        # [1, 2, 3] with weights [1,2,3]: (1*1 + 2*2 + 3*3)/6 = 14/6 ≈ 2.333
        s = _make_series([1.0, 2.0, 3.0])
        result = _wma(s, 3)
        assert float(result.iloc[-1]) == pytest.approx(14 / 6, rel=1e-6)

    def test_wma_nan_at_start(self):
        s = _make_series(list(range(1, 6)))
        result = _wma(s, 3)
        assert result.iloc[0] != result.iloc[0]  # NaN
        assert result.iloc[1] != result.iloc[1]  # NaN
        assert not (result.iloc[2] != result.iloc[2])  # not NaN


class TestHMA:
    def test_hma_returns_series_same_length(self):
        s = _make_series(list(range(1, 31)))
        result = hma(s, 9)
        assert len(result) == 30

    def test_hma_nan_at_start(self):
        s = _make_series(list(range(1, 31)))
        result = hma(s, 9)
        # First several values should be NaN due to rolling windows
        assert result.isna().any()
        assert not result.isna().all()

    def test_hma_period_1_equals_input(self):
        # HMA(1) = WMA(2*WMA(1/2=1) - WMA(1), sqrt(1)=1) = WMA(2*x - x, 1) = x
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        s = _make_series(values)
        result = hma(s, 1)
        valid = result.dropna()
        assert len(valid) == 5
        assert valid.tolist() == pytest.approx(values, rel=1e-6)

    def test_hma_with_flat_series(self):
        s = _make_series([50.0] * 30)
        result = hma(s, 9)
        valid = result.dropna()
        # All values should equal 50.0 for a flat series
        assert all(abs(v - 50.0) < 1e-6 for v in valid)

    def test_hma_with_trending_series(self):
        # Linearly increasing series → HMA should also be increasing
        s = _make_series(list(range(1, 51)))
        result = hma(s, 9)
        valid = result.dropna().tolist()
        for i in range(1, len(valid)):
            assert valid[i] >= valid[i - 1] - 1e-6

    def test_hma_output_has_no_inf(self):
        s = _make_series([100.0 + i * 0.5 for i in range(50)])
        result = hma(s, 10)
        assert not result.isin([float("inf"), float("-inf")]).any()

    def test_hma_accepts_rsi_like_series(self):
        """HMA should handle RSI values (0-100 range)."""
        rsi_values = [50.0 + 10.0 * np.sin(i * 0.3) for i in range(60)]
        s = _make_series(rsi_values)
        result = hma(s, 10)
        valid = result.dropna()
        assert len(valid) > 0
        # RSI smoothed by HMA should stay in reasonable range
        assert valid.min() > 0
        assert valid.max() < 100
