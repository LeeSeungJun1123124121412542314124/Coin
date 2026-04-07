"""Stochastic RSI indicator with K/D crossover detection.

Based on the TradingView PineScript v6 logic:
    rsiForStoch = ta.rsi(close, rsiLen)
    stochK = ta.sma(ta.stoch(rsiForStoch, rsiForStoch, rsiForStoch, stochLen), kSmoothing)
    stochD = ta.sma(stochK, dSmoothing)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate(
    df: pd.DataFrame,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_smoothing: int = 3,
    d_smoothing: int = 3,
    overbought: float = 80.0,
    oversold: float = 20.0,
    hull_rsi_value: float | None = None,
) -> dict[str, Any]:
    """Calculate Stochastic RSI with K/D crossover detection.

    Args:
        df: OHLCV DataFrame with at least ``rsi_period + stoch_period`` rows.
        rsi_period: Period for the underlying RSI calculation.
        stoch_period: Stochastic lookback period applied to the RSI series.
        k_smoothing: SMA smoothing length for the %K line.
        d_smoothing: SMA smoothing length for the %D line (signal).
        overbought: %K threshold above which the market is overbought.
        oversold: %K threshold below which the market is oversold.
        hull_rsi_value: Optional Hull RSI ribbon value for K-crossing-ribbon signal.

    Returns:
        Dict with keys:
            stoch_k, stoch_d, crossover, overbought, oversold,
            hull_rsi_crossover, k_d_gap.
    """
    close = df["close"]

    # ── Step 1: RSI (Wilder's smoothing) ─────────────────────────────
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    alpha = 1.0 / rsi_period
    avg_gain = gain.ewm(alpha=alpha, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi_series = (100.0 - (100.0 / (1.0 + rs))).fillna(100.0)

    # ── Step 2: Stochastic of RSI ─────────────────────────────────────
    rsi_lowest = rsi_series.rolling(stoch_period).min()
    rsi_highest = rsi_series.rolling(stoch_period).max()
    rsi_range = (rsi_highest - rsi_lowest).replace(0.0, float("nan"))
    stoch_raw = ((rsi_series - rsi_lowest) / rsi_range * 100.0).fillna(50.0)

    # ── Step 3: Smooth K and D ────────────────────────────────────────
    k_line = stoch_raw.rolling(k_smoothing).mean()
    d_line = k_line.rolling(d_smoothing).mean()

    current_k = float(k_line.iloc[-1]) if not pd.isna(k_line.iloc[-1]) else 50.0
    prev_k = float(k_line.iloc[-2]) if len(k_line) >= 2 and not pd.isna(k_line.iloc[-2]) else 50.0
    current_d = float(d_line.iloc[-1]) if not pd.isna(d_line.iloc[-1]) else 50.0
    prev_d = float(d_line.iloc[-2]) if len(d_line) >= 2 and not pd.isna(d_line.iloc[-2]) else 50.0

    # ── Step 4: K/D crossover ─────────────────────────────────────────
    crossover: str | None = None
    if prev_k <= prev_d and current_k > current_d:
        crossover = "bullish"
    elif prev_k >= prev_d and current_k < current_d:
        crossover = "bearish"

    # ── Step 5: K crossing Hull RSI ribbon (aggressive signal) ────────
    hull_rsi_crossover: str | None = None
    if hull_rsi_value is not None:
        if prev_k <= hull_rsi_value and current_k > hull_rsi_value:
            hull_rsi_crossover = "bullish"
        elif prev_k >= hull_rsi_value and current_k < hull_rsi_value:
            hull_rsi_crossover = "bearish"

    return {
        "stoch_k": current_k,
        "stoch_d": current_d,
        "crossover": crossover,
        "overbought": current_k > overbought,
        "oversold": current_k < oversold,
        "hull_rsi_crossover": hull_rsi_crossover,
        "k_d_gap": abs(current_k - current_d),
    }
