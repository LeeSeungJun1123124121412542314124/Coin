"""MACD (Moving Average Convergence Divergence) with crossover detection."""

from __future__ import annotations

from typing import Any

import pandas as pd


def calculate(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, Any]:
    close = df["close"]

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    current_macd = float(macd_line.iloc[-1])
    prev_macd = float(macd_line.iloc[-2])
    current_signal = float(signal_line.iloc[-1])
    prev_signal = float(signal_line.iloc[-2])
    current_hist = float(histogram.iloc[-1])
    prev_hist = float(histogram.iloc[-2])

    # Crossover detection (MACD line vs signal line)
    crossover = None
    if prev_macd <= prev_signal and current_macd > current_signal:
        crossover = "golden"
    elif prev_macd >= prev_signal and current_macd < current_signal:
        crossover = "death"

    # Histogram zero-line cross
    histogram_zero_cross = None
    if prev_hist <= 0 and current_hist > 0:
        histogram_zero_cross = "above"
    elif prev_hist >= 0 and current_hist < 0:
        histogram_zero_cross = "below"

    return {
        "macd_line": current_macd,
        "signal_line": current_signal,
        "histogram": current_hist,
        "crossover": crossover,
        "histogram_zero_cross": histogram_zero_cross,
    }
