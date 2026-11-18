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
        cloud_position = None
    elif close > max(sa, sb):
        cloud_position = "above"
    elif close < min(sa, sb):
        cloud_position = "below"
    else:
        cloud_position = "inside"

    t, k = row["tenkan"], row["kijun"]
    if t is None or k is None:
        tk_cross = None
    elif t == k:
        tk_cross = "none"
    else:
        tk_cross = "golden" if t > k else "dead"

    if n > shift:
        chikou = "above" if close > candles[n - 1 - shift]["close"] else "below"
    else:
        chikou = None

    fa, fb = ich[-1]["senkou_a"], ich[-1]["senkou_b"]
    if fa is None or fb is None:
        future_cloud = None
    else:
        future_cloud = "bullish" if fa > fb else "bearish"
    return {"cloud_position": cloud_position, "tk_cross": tk_cross, "chikou": chikou, "future_cloud": future_cloud}


def _wyckoff_box(candles: list[dict], i: int, n: int, width_pct: float) -> dict | None:
    """i번 봉 직전 n봉 박스. 폭이 width_pct 이하일 때만 박스 반환."""
    box = candles[i - n : i]
    hi = max(c["high"] for c in box)
    lo = min(c["low"] for c in box)
    avg = sum(c["close"] for c in box) / n
    if (hi - lo) / avg * 100 > width_pct:
        return None
    return {"high": hi, "low": lo, "start": box[0]["open_time"], "end": box[-1]["open_time"]}


def wyckoff_candidates(
    candles: list[dict],
    n: int = 30,
    width_pct: float = 15.0,
    vol_mult: float = 2.0,
    vol_lookback: int = 20,
) -> dict:
    """와이코프 박스권 이탈 후 복귀 봉(스프링/업스러스트) 후보와 거래량 급증 봉.

    박스는 직전 n봉. 박스 안으로 종가가 복귀한 이탈 봉만 후보이며,
    거래량 급증(vol_lookback 평균의 vol_mult배 이상)이면 strong.
    """
    spikes: list[int] = []
    cands: list[dict] = []
    for i in range(n, len(candles)):
        c = candles[i]
        spike = i >= vol_lookback and c["volume"] >= vol_mult * (
            sum(x["volume"] for x in candles[i - vol_lookback : i]) / vol_lookback
        )
        if spike:
            spikes.append(c["open_time"])
        box = _wyckoff_box(candles, i, n, width_pct)
        if box is None or not box["low"] <= c["close"] <= box["high"]:
            continue
        kinds = []
        if c["low"] < box["low"]:
            kinds.append("spring")
        if c["high"] > box["high"]:
            kinds.append("upthrust")
        for kind in kinds:
            cands.append({"time": c["open_time"], "type": kind, "strong": spike,
                          "box_high": box["high"], "box_low": box["low"]})
    current = _wyckoff_box(candles, len(candles) - 1, n, width_pct) if len(candles) > n else None
    return {"volume_spikes": spikes, "candidates": cands, "current_box": current}


def zigzag(candles: list[dict], threshold_pct: float) -> list[dict]:
    """고가·저가 기준 지그재그 확정 피벗 [{"time","price","kind"}] (고/저 교대).

    반대 방향으로 threshold_pct% 이상 되돌려야 직전 극값을 확정한다.
    마지막 미확정 극값은 내보내지 않으며, 파동 번호는 붙이지 않는다(사용자가 지정).
    """
    if len(candles) < 2:
        return []
    th = threshold_pct / 100
    pivots: list[dict] = []

    def confirm(idx: int, kind: str) -> None:
        c = candles[idx]
        pivots.append({"time": c["open_time"], "price": c["high"] if kind == "high" else c["low"], "kind": kind})

    direction = None
    hi_i = lo_i = ext = 0  # 방향 미정 상태에선 최고가 봉/최저가 봉을 따로 추적
    for i, c in enumerate(candles):
        if direction is None:
            if c["high"] >= candles[hi_i]["high"]:
                hi_i = i
            if c["low"] <= candles[lo_i]["low"]:
                lo_i = i
            if c["high"] >= candles[lo_i]["low"] * (1 + th) and lo_i != i:
                confirm(lo_i, "low")
                direction, ext = "up", i
            elif c["low"] <= candles[hi_i]["high"] * (1 - th) and hi_i != i:
                confirm(hi_i, "high")
                direction, ext = "down", i
        elif direction == "up":
            if c["high"] >= candles[ext]["high"]:
                ext = i
            if c["low"] <= candles[ext]["high"] * (1 - th):
                confirm(ext, "high")
                direction, ext = "down", i
        else:
            if c["low"] <= candles[ext]["low"]:
                ext = i
            if c["high"] >= candles[ext]["low"] * (1 + th):
                confirm(ext, "low")
                direction, ext = "up", i
    return pivots


def fib_levels(pivots: list[dict], levels: list[float]) -> list[dict]:
    """마지막 두 피벗 A(이전)·B(최근)로 B + (A-B)*level 가격을 계산. 피벗 2개 미만이면 []."""
    if len(pivots) < 2:
        return []
    a, b = pivots[-2]["price"], pivots[-1]["price"]
    return [{"level": lv, "price": b + (a - b) * lv} for lv in levels]
