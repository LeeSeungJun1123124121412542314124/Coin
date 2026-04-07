"""Outlier / black-swan circuit breaker.

Detects extreme market events using multiple indicators.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def detect(
    atr_data: dict[str, Any],
    bb_data: dict[str, Any],
    volume_data: dict[str, Any],
    price_df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Detect outlier/black-swan conditions from multi-indicator checks.

    Checks:
        1. ATR extreme spike (> atr_spike_multiplier × prev avg)
        2. Volume spike (ratio > spike_threshold — already in volume_data)
        3. Price extreme BB deviation (%B > 2.0 or < -1.0)
        4. Single candle N% move

    Severity:
        0 = normal
        1 = outlier (1+ checks triggered)
        2 = critical (2+ checks triggered)

    Returns:
        is_outlier, is_critical, severity, alerts, single_candle_pct
    """
    atr_spike_multiplier = config.get("atr_spike_multiplier", 2.0)
    single_candle_threshold = config.get("single_candle_pct", 5.0)

    alerts: list[str] = []

    # 1. ATR extreme spike
    prev_avg = atr_data.get("atr_prev_avg", 0.0)
    current_atr = atr_data.get("atr", 0.0)
    if prev_avg > 0 and current_atr > prev_avg * atr_spike_multiplier:
        alerts.append(f"ATR 극단 스파이크 ({current_atr / prev_avg:.1f}×)")

    # 2. Volume spike
    if volume_data and volume_data.get("spike", False):
        ratio = volume_data.get("volume_ratio", 0.0)
        alerts.append(f"거래량 급등 ({ratio:.1f}×)")

    # 3. BB extreme deviation (%B > 2.0 or < -1.0)
    percent_b = bb_data.get("percent_b", 0.5)
    if percent_b > 2.0:
        alerts.append(f"%B 극단 상단 이탈 ({percent_b:.2f})")
    elif percent_b < -1.0:
        alerts.append(f"%B 극단 하단 이탈 ({percent_b:.2f})")

    # 4. Single candle move
    single_candle_pct = 0.0
    if len(price_df) >= 1:
        last = price_df.iloc[-1]
        open_p = float(last.get("open", last["close"]))
        close_p = float(last["close"])
        if open_p > 0:
            single_candle_pct = abs(close_p - open_p) / open_p * 100.0
            if single_candle_pct >= single_candle_threshold:
                alerts.append(f"단일 캔들 급변 ({single_candle_pct:.1f}%)")

    severity = min(2, len(alerts))

    return {
        "is_outlier": severity >= 1,
        "is_critical": severity >= 2,
        "severity": severity,
        "alerts": alerts,
        "single_candle_pct": single_candle_pct,
    }
