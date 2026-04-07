"""Historical Volatility indicator (annualized standard deviation of log returns)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate(df: pd.DataFrame, period: int = 20, timeframe: str = "1h") -> float:
    _TF_PERIODS_PER_YEAR: dict[str, int] = {
        "1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
        "1h": 8_760, "2h": 4_380, "4h": 2_190, "6h": 1_460,
        "12h": 730, "1d": 365,
    }
    close = df["close"]
    log_returns = np.log(close / close.shift(1))
    periods_per_year = _TF_PERIODS_PER_YEAR.get(timeframe, 8_760)
    hv = log_returns.rolling(period).std().iloc[-1] * np.sqrt(periods_per_year) * 100
    return float(hv)
