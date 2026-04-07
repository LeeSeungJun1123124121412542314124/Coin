"""Heikin Ashi filter — candle-based signal confirmation.

Three filter modes (matching TradingView indicator logic):
  - simple  : HA candle color matches signal direction
  - strong  : HA candle has no opposing wick (stronger confirmation)
  - safe    : 2 consecutive HA candles confirm direction
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def calculate(
    df: pd.DataFrame,
    mode: str = "simple",
) -> dict[str, Any]:
    """Calculate Heikin Ashi candles and apply directional confirmation filter.

    Args:
        df: OHLCV DataFrame with open, high, low, close columns.
        mode: Filter strictness — ``"simple"``, ``"strong"``, or ``"safe"``.

    Returns:
        Dict with keys:
            ha_bullish, ha_bearish, filter_bullish, filter_bearish,
            ha_close, ha_open, ha_high, ha_low, mode.
    """
    # ── Heikin Ashi candle calculation ────────────────────────────────
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0

    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0

    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)

    # ── Current candle direction ──────────────────────────────────────
    curr_bullish = bool(ha_close.iloc[-1] > ha_open.iloc[-1])
    curr_bearish = bool(ha_close.iloc[-1] < ha_open.iloc[-1])

    # Previous candle (for safe mode)
    prev_bullish = bool(ha_close.iloc[-2] > ha_open.iloc[-2]) if len(df) >= 2 else False
    prev_bearish = bool(ha_close.iloc[-2] < ha_open.iloc[-2]) if len(df) >= 2 else False

    # ── Strong mode: no opposing wick ────────────────────────────────
    # Bullish strong: no lower wick (ha_low ≈ ha_open)
    # Bearish strong: no upper wick (ha_high ≈ ha_open)
    _tick = 1e-8
    curr_strong_bullish = curr_bullish and (ha_open.iloc[-1] - ha_low.iloc[-1] < _tick)
    curr_strong_bearish = curr_bearish and (ha_high.iloc[-1] - ha_open.iloc[-1] < _tick)

    # ── Apply filter mode ─────────────────────────────────────────────
    if mode == "strong":
        filter_bullish = bool(curr_strong_bullish)
        filter_bearish = bool(curr_strong_bearish)
    elif mode == "safe":
        filter_bullish = bool(curr_bullish and prev_bullish)
        filter_bearish = bool(curr_bearish and prev_bearish)
    else:  # "simple"
        filter_bullish = curr_bullish
        filter_bearish = curr_bearish

    return {
        "ha_bullish": curr_bullish,
        "ha_bearish": curr_bearish,
        "filter_bullish": filter_bullish,
        "filter_bearish": filter_bearish,
        "ha_close": float(ha_close.iloc[-1]),
        "ha_open": float(ha_open.iloc[-1]),
        "ha_high": float(ha_high.iloc[-1]),
        "ha_low": float(ha_low.iloc[-1]),
        "mode": mode,
    }
