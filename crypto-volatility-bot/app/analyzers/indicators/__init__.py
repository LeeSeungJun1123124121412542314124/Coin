"""Indicator registry — maps indicator name to calculate function."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from app.analyzers.indicators import (
    atr,
    bollinger_width,
    cvi,
    historical_volatility,
    mfi,
    obv,
    volume_spike,
    vwap,
)

REGISTRY: dict[str, Callable[[pd.DataFrame, int], float]] = {
    "atr": atr.calculate,
    "bollinger_width": bollinger_width.calculate,
    "cvi": cvi.calculate,
    "historical_volatility": historical_volatility.calculate,
    "mfi": mfi.calculate,
    "obv": obv.calculate,
    "volume_spike": volume_spike.calculate,
    "vwap": vwap.calculate,
}
