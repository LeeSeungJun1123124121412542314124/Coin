"""Relative Strength Index (RSI) with Wilder's smoothing.

Divergence detection with configurable parameters.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate(
    df: pd.DataFrame,
    period: int = 14,
    divergence_lookback: int = 60,
    overbought: float = 70.0,
    oversold: float = 30.0,
    divergence_order: int = 5,
    min_peak_distance: int = 10,
    min_divergence_pct: float = 0.5,
    hull_smooth_period: int | None = None,
) -> dict[str, Any]:
    """Calculate RSI with optional Hull MA smoothing for divergence detection.

    Args:
        hull_smooth_period: If set, smooth RSI with HMA before peak/valley
            detection. Produces cleaner divergence signals by reducing noise.
            ``None`` (default) preserves original behaviour.
    """
    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi_series = 100.0 - (100.0 / (1.0 + rs))
    rsi_series = rsi_series.fillna(100.0)

    current_rsi = float(rsi_series.iloc[-1])

    # Optional Hull MA smoothing before divergence detection
    rsi_for_divergence = rsi_series
    if hull_smooth_period is not None:
        from app.analyzers.indicators.hull_ma import hma  # local import avoids circularity
        smoothed = hma(rsi_series, hull_smooth_period)
        # Only use smoothed series if it has enough non-NaN values
        if smoothed.notna().sum() >= 2:
            rsi_for_divergence = smoothed

    # Divergence detection
    divergence, divergence_detail, divergence_magnitude = _detect_divergence(
        close,
        rsi_for_divergence,
        divergence_lookback,
        order=divergence_order,
        min_peak_distance=min_peak_distance,
        min_divergence_pct=min_divergence_pct,
    )

    return {
        "rsi": current_rsi,
        "rsi_series": rsi_series,          # exposed for Hull RSI Ribbon calculation
        "overbought": current_rsi > overbought,
        "oversold": current_rsi < oversold,
        "divergence": divergence,
        "divergence_detail": divergence_detail,
        "divergence_magnitude": divergence_magnitude,
    }


def _find_local_peaks(series: pd.Series, order: int = 5) -> list[int]:
    """Find local maxima indices using left/right comparison."""
    values = series.values
    n = len(values)
    peaks = []
    for i in range(order, n - order):
        if all(values[i] > values[i - j] for j in range(1, order + 1)) and all(
            values[i] > values[i + j] for j in range(1, order + 1)
        ):
            peaks.append(i)
    return peaks


def _find_local_valleys(series: pd.Series, order: int = 5) -> list[int]:
    """Find local minima indices using left/right comparison."""
    values = series.values
    n = len(values)
    valleys = []
    for i in range(order, n - order):
        if all(values[i] < values[i - j] for j in range(1, order + 1)) and all(
            values[i] < values[i + j] for j in range(1, order + 1)
        ):
            valleys.append(i)
    return valleys


def _detect_divergence(
    price: pd.Series,
    rsi: pd.Series,
    lookback: int,
    order: int = 5,
    min_peak_distance: int = 10,
    min_divergence_pct: float = 0.5,
) -> tuple[str | None, str | None, float]:
    """Detect bearish/bullish divergence between price and RSI.

    Returns (divergence_type, detail_text, magnitude_pct).

    Bearish: price makes higher high, RSI makes lower high
    Bullish: price makes lower low, RSI makes higher low
    """
    if len(price) < lookback:
        lookback = len(price)

    price_tail = price.iloc[-lookback:]
    rsi_tail = rsi.iloc[-lookback:]

    # Check bearish divergence (peaks)
    price_peaks = _find_local_peaks(price_tail, order=order)
    if len(price_peaks) >= 2:
        p1, p2 = price_peaks[-2], price_peaks[-1]
        # Minimum peak distance filter
        if p2 - p1 >= min_peak_distance:
            price_val1 = price_tail.iloc[p1]
            price_val2 = price_tail.iloc[p2]
            rsi_val1 = rsi_tail.iloc[p1]
            rsi_val2 = rsi_tail.iloc[p2]
            # Minimum price change filter
            if price_val1 > 0:
                price_chg_pct = abs(price_val2 - price_val1) / price_val1 * 100.0
                if price_chg_pct >= min_divergence_pct:
                    if price_val2 > price_val1 and rsi_val2 < rsi_val1:
                        magnitude = price_chg_pct
                        return "bearish", "가격 고점↑ RSI 고점↓", magnitude

    # Check bullish divergence (valleys)
    price_valleys = _find_local_valleys(price_tail, order=order)
    if len(price_valleys) >= 2:
        v1, v2 = price_valleys[-2], price_valleys[-1]
        # Minimum peak distance filter
        if v2 - v1 >= min_peak_distance:
            price_val1 = price_tail.iloc[v1]
            price_val2 = price_tail.iloc[v2]
            rsi_val1 = rsi_tail.iloc[v1]
            rsi_val2 = rsi_tail.iloc[v2]
            # Minimum price change filter
            if price_val1 > 0:
                price_chg_pct = abs(price_val2 - price_val1) / price_val1 * 100.0
                if price_chg_pct >= min_divergence_pct:
                    if price_val2 < price_val1 and rsi_val2 > rsi_val1:
                        magnitude = price_chg_pct
                        return "bullish", "가격 저점↓ RSI 저점↑", magnitude

    return None, None, 0.0
