"""Volume Weighted Average Price (VWAP) indicator."""

from __future__ import annotations

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 20) -> float:
    """VWAP 계산 후 마지막 값 반환.

    period 파라미터는 REGISTRY 인터페이스 일관성을 위해 수용.
    일중 세션 VWAP이 아닌 rolling period 기반 VWAP을 계산.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["volume"]

    tp_vol = typical_price * volume
    vwap_series = tp_vol.rolling(period).sum() / volume.rolling(period).sum()

    last_val = vwap_series.iloc[-1]
    if pd.isna(last_val):
        return float(typical_price.iloc[-1])
    return float(last_val)


def get_deviation_pct(df: pd.DataFrame, period: int = 20) -> float | None:
    """현재가의 VWAP 대비 이탈률(%) 반환.

    Returns:
        양수 = 현재가가 VWAP 위, 음수 = 아래
        None = 데이터 부족
    """
    vwap = calculate(df, period)
    if vwap == 0:
        return None
    current_price = float(df["close"].iloc[-1])
    return (current_price - vwap) / vwap * 100.0
