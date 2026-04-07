"""Volume Spike indicator — ratio of last bar volume to rolling average."""

from __future__ import annotations

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 20) -> float:
    volume = df["volume"]
    rolling_mean = volume.rolling(period).mean()
    ratio = (volume / rolling_mean).iloc[-1]
    return float(ratio)
