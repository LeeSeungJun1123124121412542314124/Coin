"""Money Flow Index (MFI) indicator."""

from __future__ import annotations

import pandas as pd


def calculate(df: pd.DataFrame, period: int = 14) -> float:
    """MFI 계산 후 마지막 값 반환 (0~100).

    MFI = 100 - 100 / (1 + Money Flow Ratio)
    Money Flow Ratio = Positive MF / Negative MF
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume

    # 전일 대비 전형가 방향
    tp_diff = typical_price.diff()
    positive_mf = money_flow.where(tp_diff > 0, 0.0)
    negative_mf = money_flow.where(tp_diff < 0, 0.0)

    pos_sum = positive_mf.rolling(period).sum()
    neg_sum = negative_mf.rolling(period).sum()

    # 0 나눗셈 방지
    mfr = pos_sum / neg_sum.replace(0, float("nan"))
    mfi_series = 100 - (100 / (1 + mfr))

    last_val = mfi_series.iloc[-1]
    if pd.isna(last_val):
        return 50.0  # 데이터 부족 시 중립
    return float(last_val)
