"""Bollinger Bands with squeeze detection and middle-line break."""

from __future__ import annotations

from typing import Any

import pandas as pd


def calculate(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> dict[str, Any]:
    close = df["close"]
    ma = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)

    upper = ma + std_dev * std
    lower = ma - std_dev * std

    current_upper = float(upper.iloc[-1])
    current_middle = float(ma.iloc[-1])
    current_lower = float(lower.iloc[-1])
    current_close = float(close.iloc[-1])

    band_width = current_upper - current_lower
    if current_middle != 0:
        bandwidth_pct = band_width / current_middle
    else:
        bandwidth_pct = 0.0

    # %B
    if band_width != 0:
        percent_b = (current_close - current_lower) / band_width
    else:
        percent_b = 0.5

    # Squeeze: current bandwidth below 50% of the overall historical average
    bandwidth_series = (upper - lower) / ma
    bw_valid = bandwidth_series.dropna()
    historical_bw_avg = float(bw_valid.mean()) if len(bw_valid) > 0 else 0.0
    squeeze = bandwidth_pct < historical_bw_avg * 0.5 if historical_bw_avg > 0 else False

    # Middle line break detection
    prev_close = float(close.iloc[-2])
    prev_middle = float(ma.iloc[-2])
    middle_line_break = None
    if prev_close <= prev_middle and current_close > current_middle:
        middle_line_break = "above"
    elif prev_close >= prev_middle and current_close < current_middle:
        middle_line_break = "below"

    # Expansion direction (for squeeze→expansion)
    prev_bw = float(bandwidth_series.iloc[-2]) if len(bandwidth_series) >= 2 else 0.0
    expanding = bandwidth_pct > prev_bw

    return {
        "upper": current_upper,
        "middle": current_middle,
        "lower": current_lower,
        "bandwidth": bandwidth_pct,
        "bandwidth_prev": prev_bw,
        "bandwidth_series": bandwidth_series,
        "percent_b": percent_b,
        "squeeze": squeeze,
        "expanding": expanding,
        "price_above_middle": current_close > current_middle,
        "middle_line_break": middle_line_break,
    }
