"""학습 탭 지표 계산 (순수 함수, DB/네트워크 없음)."""

from __future__ import annotations

from datetime import datetime, timezone

INTERVALS: tuple[str, ...] = ("1h", "4h", "1d", "1w", "1M")
_FIXED_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}


def next_open_time(t_ms: int, interval: str) -> int:
    """t_ms 봉의 다음 봉 open_time(ms). 1M은 다음 달 1일 00:00 UTC."""
    if interval in _FIXED_MS:
        return t_ms + _FIXED_MS[interval]
    if interval == "1M":
        d = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)
        y, m = divmod(d.year * 12 + d.month, 12)  # d.month는 1부터라 그대로 다음 달 인덱스(0부터)가 된다
        return int(datetime(y, m + 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    raise ValueError(f"지원하지 않는 interval: {interval}")


def _mid(candles: list[dict], i: int, period: int) -> float | None:
    """i번 봉까지 period개 봉의 (최고가+최저가)/2. 봉이 부족하면 None."""
    if i < period - 1:
        return None
    win = candles[i - period + 1 : i + 1]
    return (max(c["high"] for c in win) + min(c["low"] for c in win)) / 2


def ichimoku(
    candles: list[dict],
    interval: str,
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
    times = [c["open_time"] for c in candles]
    for _ in range(shift):
        times.append(next_open_time(times[-1], interval))
    rows = [
        {"time": t, "tenkan": None, "kijun": None, "senkou_a": None, "senkou_b": None, "chikou": None}
        for t in times
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
                continue  # 같은 봉 안의 고저 순서는 알 수 없으므로 되돌림 확정은 다음 봉부터
            if c["low"] <= candles[ext]["high"] * (1 - th):
                confirm(ext, "high")
                direction, ext = "down", i
        else:
            if c["low"] <= candles[ext]["low"]:
                ext = i
                continue  # 같은 봉 안의 고저 순서는 알 수 없으므로 되돌림 확정은 다음 봉부터
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


def sma(values: list[float], n: int) -> list[float | None]:
    """단순 이동평균. 앞 n-1개는 None."""
    out: list[float | None] = [None] * len(values)
    for i in range(n - 1, len(values)):
        out[i] = sum(values[i - n + 1 : i + 1]) / n
    return out


def ema(values: list[float], n: int) -> list[float | None]:
    """지수 이동평균(α=2/(n+1)). 첫 값은 첫 n개의 SMA, 앞 n-1개는 None."""
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    alpha = 2 / (n + 1)
    for i in range(n, len(values)):
        prev = (values[i] - prev) * alpha + prev
        out[i] = prev
    return out


def bollinger(values: list[float], n: int, k: float) -> list[dict | None]:
    """볼린저밴드 = n봉 SMA ± k × 모표준편차."""
    out: list[dict | None] = [None] * len(values)
    for i in range(n - 1, len(values)):
        win = values[i - n + 1 : i + 1]
        mid = sum(win) / n
        sd = (sum((x - mid) ** 2 for x in win) / n) ** 0.5
        out[i] = {"upper": mid + k * sd, "mid": mid, "lower": mid - k * sd}
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def rsi(values: list[float], n: int) -> list[float | None]:
    """RSI(와일더 평활). 첫 값은 n개 변화량의 평균 상승·하락, 앞 n개는 None."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= n:
        return out
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    avg_gain = sum(max(d, 0) for d in diffs[:n]) / n
    avg_loss = sum(max(-d, 0) for d in diffs[:n]) / n
    out[n] = _rsi_value(avg_gain, avg_loss)
    for i in range(n + 1, len(values)):
        d = diffs[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(d, 0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-d, 0)) / n
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def macd(values: list[float], fast: int, slow: int, signal: int) -> list[dict | None]:
    """MACD = EMA(fast) − EMA(slow), 시그널 = MACD의 EMA, 히스토그램 = MACD − 시그널."""
    out: list[dict | None] = [None] * len(values)
    ef, es = ema(values, fast), ema(values, slow)
    line = [f - s if f is not None and s is not None else None for f, s in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), None)
    if start is None:
        return out
    sig = ema(line[start:], signal)
    for j, sv in enumerate(sig):
        if sv is not None:
            m = line[start + j]
            out[start + j] = {"macd": m, "signal": sv, "hist": m - sv}
    return out


def indicator_warmup(cfg: dict) -> int:
    """켜진 보조 지표 계산에 필요한 앞쪽 추가 봉 수. 최소 52, 상한 1500."""
    need = [52]
    if cfg["ma"]["enabled"]:
        need.append(max(cfg["ma"]["periods"]))
    if cfg["bb"]["enabled"]:
        need.append(cfg["bb"]["period"])
    if cfg["rsi"]["enabled"]:
        need.append(cfg["rsi"]["period"] * 3)
    if cfg["macd"]["enabled"]:
        need.append((cfg["macd"]["slow"] + cfg["macd"]["signal"]) * 3)
    return min(max(need), 1500)
