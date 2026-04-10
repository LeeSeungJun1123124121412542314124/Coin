"""On-Balance Volume (OBV) indicator."""

from __future__ import annotations

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 20) -> float:
    """OBV 계산 후 마지막 값 반환 (정규화용 스칼라).

    period 파라미터는 REGISTRY 인터페이스 일관성을 위해 수용하지만 미사용.
    """
    close = df["close"]
    volume = df["volume"]
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv_series = (volume * direction).cumsum()
    return float(obv_series.iloc[-1])


def get_divergence(df: pd.DataFrame, lookback: int = 14) -> str | None:
    """OBV 다이버전스 감지.

    Returns:
        "bearish"  — 가격 상승 + OBV 하락 (가짜 상승)
        "bullish"  — 가격 하락 + OBV 상승 (반등 신호)
        None       — 다이버전스 없음
    """
    if len(df) < lookback + 1:
        return None

    close = df["close"]
    volume = df["volume"]
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv_series = (volume * direction).cumsum()

    price_start = float(close.iloc[-(lookback + 1)])
    price_end = float(close.iloc[-1])
    obv_start = float(obv_series.iloc[-(lookback + 1)])
    obv_end = float(obv_series.iloc[-1])

    price_up = price_end > price_start
    obv_up = obv_end > obv_start

    if price_up and not obv_up:
        return "bearish"
    if not price_up and obv_up:
        return "bullish"
    return None
