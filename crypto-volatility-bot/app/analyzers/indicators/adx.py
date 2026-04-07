"""Average Directional Index (ADX) with +DI/-DI and crossover detection."""

from __future__ import annotations

from typing import Any

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 14) -> dict[str, Any]:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / period
    atr_ema = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    plus_di = 100 * (
        plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_ema
    )
    minus_di = 100 * (
        minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_ema
    )

    di_sum = plus_di + minus_di
    dx = ((plus_di - minus_di).abs() / di_sum.replace(0.0, float("nan"))) * 100
    adx_series = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    current_adx = adx_series.iloc[-1]
    prev_adx = adx_series.iloc[-2]
    current_plus_di = plus_di.iloc[-1]
    current_minus_di = minus_di.iloc[-1]
    prev_plus_di = plus_di.iloc[-2]
    prev_minus_di = minus_di.iloc[-2]

    # DI crossover detection
    di_crossover = None
    if prev_plus_di > prev_minus_di and current_minus_di >= current_plus_di:
        di_crossover = "bearish"
    elif prev_minus_di > prev_plus_di and current_plus_di >= current_minus_di:
        di_crossover = "bullish"

    adx_val = 0.0 if pd.isna(current_adx) else float(current_adx)
    prev_adx_val = 0.0 if pd.isna(prev_adx) else float(prev_adx)

    return {
        "adx": adx_val,
        "adx_prev": prev_adx_val,
        "plus_di": 0.0 if pd.isna(current_plus_di) else float(current_plus_di),
        "minus_di": 0.0 if pd.isna(current_minus_di) else float(current_minus_di),
        "adx_declining": adx_val < prev_adx_val,
        "di_crossover": di_crossover,
    }
