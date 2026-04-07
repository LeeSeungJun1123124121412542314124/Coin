"""Hull Moving Average (HMA) — fast, low-lag moving average utility.

HMA(n) = WMA(2 * WMA(n/2) - WMA(n), sqrt(n))

Used for smoothing RSI and as a trend baseline in the Hull RSI Ribbon.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def hma(series: pd.Series, period: int) -> pd.Series:
    """Calculate Hull Moving Average.

    Args:
        series: Input price or indicator series.
        period: HMA period (e.g. 10 for RSI smoothing, 30 for trend baseline).

    Returns:
        pd.Series of HMA values (NaN-padded at the start).
    """
    half_period = max(1, period // 2)
    sqrt_period = max(1, int(math.sqrt(period)))

    wma_half = _wma(series, half_period)
    wma_full = _wma(series, period)

    diff = 2.0 * wma_half - wma_full
    return _wma(diff, sqrt_period)


def _wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average — weights linearly increase from 1 to period."""
    weights = np.arange(1, period + 1, dtype=float)
    total_weight = weights.sum()

    return series.rolling(window=period).apply(
        lambda x: float(np.dot(x, weights) / total_weight),
        raw=True,
    )
