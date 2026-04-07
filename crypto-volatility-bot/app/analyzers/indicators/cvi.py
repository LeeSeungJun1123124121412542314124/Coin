"""Chaikin Volatility Index (CVI) indicator.

CVI = (EMA(H-L, period) - EMA(H-L, period).shift(period)) / EMA(H-L, period).shift(period) * 100
"""

from __future__ import annotations

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 10) -> float:
    hl = df["high"] - df["low"]
    ema = hl.ewm(span=period, adjust=False).mean()
    ema_shifted = ema.shift(period)
    cvi = ((ema - ema_shifted) / ema_shifted * 100).iloc[-1]
    return float(cvi)
