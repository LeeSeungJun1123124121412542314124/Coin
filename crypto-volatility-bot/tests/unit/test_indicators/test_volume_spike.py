"""Tests for Volume Spike indicator."""

import numpy as np
import pandas as pd

from app.analyzers.indicators.volume_spike import calculate


def test_volume_spike_returns_positive_float(sample_ohlcv_df):
    result = calculate(sample_ohlcv_df, period=20)
    assert isinstance(result, float)
    assert result > 0


def test_volume_spike_near_one_for_normal_volume(sample_ohlcv_df):
    # Normal fixture has uniform volume, ratio should be near 1.0
    result = calculate(sample_ohlcv_df, period=20)
    assert 0.1 < result < 10.0


def test_volume_spike_high_on_last_bar():
    df = pd.DataFrame(
        {
            "open": np.ones(30),
            "high": np.ones(30),
            "low": np.ones(30),
            "close": np.ones(30),
            "volume": [100.0] * 29 + [5000.0],
        }
    )
    result = calculate(df, period=20)
    assert result > 10
