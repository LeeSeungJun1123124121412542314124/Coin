"""Bollinger Band Width indicator."""

from __future__ import annotations

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 20) -> float:
    close = df["close"]
    ma = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = ma + 2 * std
    lower = ma - 2 * std
    # Normalized width = (upper - lower) / ma
    width = ((upper - lower) / ma).iloc[-1]
    return float(width)
