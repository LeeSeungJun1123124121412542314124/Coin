"""학습 탭 지표 계산 (순수 함수, DB/네트워크 없음)."""

from __future__ import annotations


def _mid(candles: list[dict], i: int, period: int) -> float | None:
    """i번 봉까지 period개 봉의 (최고가+최저가)/2. 봉이 부족하면 None."""
    if i < period - 1:
        return None
    win = candles[i - period + 1 : i + 1]
    return (max(c["high"] for c in win) + min(c["low"] for c in win)) / 2


def ichimoku(
    candles: list[dict],
    interval_ms: int,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
    shift: int = 26,
) -> list[dict]:
    """일목균형표 전체 요소. 선행스팬은 shift봉 앞, 후행스팬은 shift봉 뒤로 민다.

    마지막 봉 뒤로 shift개의 미래 시각을 덧붙여 선행스팬만 채운다.
    """
    n = len(candles)
    if n == 0:
        return []
    last = candles[-1]["open_time"]
    rows = [
        {"time": candles[i]["open_time"] if i < n else last + (i - n + 1) * interval_ms,
         "tenkan": None, "kijun": None, "senkou_a": None, "senkou_b": None, "chikou": None}
        for i in range(n + shift)
    ]
    for i in range(n):
        t = _mid(candles, i, tenkan)
        k = _mid(candles, i, kijun)
        rows[i]["tenkan"] = t
        rows[i]["kijun"] = k
        # 선행스팬: i봉에서 계산한 값을 i+shift 위치에 표시
        rows[i + shift]["senkou_a"] = (t + k) / 2 if t is not None and k is not None else None
        rows[i + shift]["senkou_b"] = _mid(candles, i, senkou_b)
        # 후행스팬: i봉 종가를 i-shift 위치에 표시
        if i - shift >= 0:
            rows[i - shift]["chikou"] = candles[i]["close"]
    return rows


def ichimoku_state(candles: list[dict], ich: list[dict]) -> dict:
    """마지막 마감 봉 기준 일목 상태 요약."""
    n = len(candles)
    shift = len(ich) - n
    row = ich[n - 1]
    close = candles[-1]["close"]
    sa, sb = row["senkou_a"], row["senkou_b"]
    if sa is None or sb is None:
        cloud_position = "none"
    elif close > max(sa, sb):
        cloud_position = "above"
    elif close < min(sa, sb):
        cloud_position = "below"
    else:
        cloud_position = "inside"

    t, k = row["tenkan"], row["kijun"]
    if t is None or k is None or t == k:
        tk_cross = "none"
    else:
        tk_cross = "golden" if t > k else "dead"

    chikou = "above" if n > shift and close > candles[n - 1 - shift]["close"] else "below"

    fa, fb = ich[-1]["senkou_a"], ich[-1]["senkou_b"]
    future_cloud = "bullish" if fa is not None and fb is not None and fa > fb else "bearish"
    return {"cloud_position": cloud_position, "tk_cross": tk_cross, "chikou": chikou, "future_cloud": future_cloud}
