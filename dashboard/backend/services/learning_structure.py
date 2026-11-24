"""학습 탭 HTF-LTF 구조 점수와 구조 가격 범위 (순수 함수, DB/네트워크 없음).

입력 캔들은 {open_time, open, high, low, close, volume} dict 리스트(시간 오름차순).
규칙 근거는 docs/plans/htf-ltf-score-spec-2026-11-24.md.
"""

from __future__ import annotations

# 보고 있는 시간봉 -> 상위 시간봉 (월봉은 상위 없음)
HTF_OF: dict[str, str | None] = {"1h": "1d", "4h": "1d", "1d": "1w", "1w": "1M", "1M": None}
_NAMES = {"1h": "1시간봉", "4h": "4시간봉", "1d": "일봉", "1w": "주봉", "1M": "월봉"}

MIN_BARS = 60            # 이보다 적으면 구조 판정 불가(insufficient)
FRESH_BARS = 20          # 마지막 돌파가 이 봉 수 이내면 신선
HTF_FRESH, HTF_STALE = 20, 5
LTF_FRESH, LTF_STALE = 20, 10
AGREE_BONUS = 10         # 상·하위가 같은 방향이고 둘 다 신선할 때
BULLISH_MIN, BEARISH_MAX = 65, 40


def _next_level(points: list[dict], higher: bool) -> list[dict]:
    """점들 중 가운데가 양옆보다 (higher면 높고, 아니면 낮은) 것. 확정 시점은 오른쪽 이웃의 확정 시점."""
    out = []
    for j in range(1, len(points) - 1):
        p, left, right = points[j]["price"], points[j - 1]["price"], points[j + 1]["price"]
        if (p > left and p > right) if higher else (p < left and p < right):
            out.append({"idx": points[j]["idx"], "price": p, "confirm": points[j + 1]["confirm"]})
    return out


def swings(candles: list[dict]) -> dict[str, list[dict]]:
    """단기·중기·장기 스윙 고점/저점. 각 항목은 {idx, price, confirm}.

    confirm은 스윙이 확정되는 봉 인덱스(오른쪽 봉이 마감된 시점). 같은 값은 스윙으로 치지 않는다.
    """
    out: dict[str, list[dict]] = {}
    for higher, key in ((True, "high"), (False, "low")):
        short = []
        for i in range(1, len(candles) - 1):
            a, b, c = candles[i - 1][key], candles[i][key], candles[i + 1][key]
            if (b > a and b > c) if higher else (b < a and b < c):
                short.append({"idx": i, "price": b, "confirm": i + 1})
        mid = _next_level(short, higher)
        out[f"short_{key}"] = short
        out[f"mid_{key}"] = mid
        out[f"long_{key}"] = _next_level(mid, higher)
    return out


def _scan(candles: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    """구조 돌파 목록과, 마지막 봉 처리 뒤 확정돼 있고 안 깨진 스윙 목록(active)을 함께 구한다."""
    sw = swings(candles)
    names = ("mid_high", "long_high", "mid_low", "long_low")
    pos = {n: 0 for n in names}
    active: dict[str, list[dict]] = {n: [] for n in names}
    breaks: list[dict] = []
    for t, c in enumerate(candles):
        for n in names:
            while pos[n] < len(sw[n]) and sw[n][pos[n]]["confirm"] <= t:
                active[n].append(sw[n][pos[n]])
                pos[n] += 1
        close = c["close"]
        for direction, mid_n, long_n in (("up", "mid_high", "long_high"), ("down", "mid_low", "long_low")):
            up = direction == "up"
            m = active[mid_n][-1]["price"] if active[mid_n] else None
            g = active[long_n][-1]["price"] if active[long_n] else None
            beat = (lambda lv: close > lv) if up else (lambda lv: close < lv)
            if not ((m is not None and beat(m)) or (g is not None and beat(g))):
                continue
            strong = g is not None and beat(g)
            for n in (mid_n, long_n):  # 넘긴 스윙은 깨진 것으로 본다
                active[n] = [s for s in active[n] if not beat(s["price"])]
            breaks.append({
                "idx": t, "time": c["open_time"], "level": g if strong else m, "direction": direction,
                "kind": "choch" if breaks and breaks[-1]["direction"] != direction else "bos",
                "strength": "strong" if strong else "weak",
            })
            break
    return breaks, active


def structure_breaks(candles: list[dict]) -> list[dict]:
    """종가 기준 구조 돌파(MSB)를 시간순으로 반환. 미래 정보는 쓰지 않는다.

    각 시점에 확정된, 아직 안 깨진 가장 최근 중기/장기 스윙을 종가가 넘으면 돌파.
    장기 스윙을 넘으면 strong, 중기만 넘으면 weak. 직전 돌파와 같은 방향이면 bos, 반대면 choch
    (첫 돌파는 bos). 항목: {idx, time, level, direction, kind, strength}.
    """
    return _scan(candles)[0]


def structure_state(candles: list[dict]) -> dict:
    """시간봉 1개의 구조 상태 {trend, fresh, insufficient, last_break, range}.

    range는 마지막 봉 시점에 확정돼 있고 종가로 안 깨진 가장 최근 중기 고점/저점(돌파 판정에 쓰는 레벨).
    """
    if len(candles) < MIN_BARS:
        return {"trend": "neutral", "fresh": False, "insufficient": True, "last_break": None,
                "range": {"high": None, "low": None}}
    breaks, active = _scan(candles)
    rng = {"high": active["mid_high"][-1]["price"] if active["mid_high"] else None,
           "low": active["mid_low"][-1]["price"] if active["mid_low"] else None}
    if not breaks:
        return {"trend": "neutral", "fresh": False, "insufficient": False, "last_break": None, "range": rng}
    b = breaks[-1]
    bars_ago = len(candles) - 1 - b["idx"]
    last = {k: b[k] for k in ("time", "level", "direction", "kind", "strength")} | {"bars_ago": bars_ago}
    return {"trend": b["direction"], "fresh": bars_ago <= FRESH_BARS, "insufficient": False,
            "last_break": last, "range": rng}


def _contrib(state: dict, name: str | None, fresh_pts: int, stale_pts: int) -> tuple[int, str]:
    """상태 하나의 점수 기여와 근거 문장."""
    if name is None:
        return 0, "월봉: 상위 시간봉 없음, 중립 0"
    if state["insufficient"]:
        return 0, f"{name}: 캔들 부족, 중립 0"
    if state["trend"] == "neutral":
        return 0, f"{name}: 구조 중립 0"
    b = state["last_break"]
    pts = (fresh_pts if state["fresh"] else stale_pts) * (1 if state["trend"] == "up" else -1)
    word = "상승" if state["trend"] == "up" else "하락"
    shape = "전환" if b["kind"] == "choch" else "구조"
    strength = "강" if b["strength"] == "strong" else "약"
    age = "신선" if state["fresh"] else "오래됨"
    kind = "BoS" if b["kind"] == "bos" else "CHoCH"
    return pts, f"{name}: {word} {shape}({kind}, {strength}), 마지막 돌파 {b['bars_ago']}봉 전({age}) {pts:+d}"


def score_structure(htf: dict, ltf: dict, htf_interval: str | None, ltf_interval: str) -> dict:
    """HTF·LTF 구조 상태 -> {score, label, reasons, htf_pts, ltf_pts, bonus}."""
    h_pts, h_reason = _contrib(htf, _NAMES.get(htf_interval), HTF_FRESH, HTF_STALE)
    l_pts, l_reason = _contrib(ltf, _NAMES[ltf_interval], LTF_FRESH, LTF_STALE)
    reasons = [h_reason, l_reason]
    bonus = 0
    if htf["trend"] == ltf["trend"] != "neutral" and htf["fresh"] and ltf["fresh"]:
        bonus = AGREE_BONUS if ltf["trend"] == "up" else -AGREE_BONUS
        reasons.append(f"상·하위 시간봉 같은 방향(둘 다 신선) {bonus:+d}")
    score = max(0, min(100, 50 + h_pts + l_pts + bonus))
    label = "bearish" if score <= BEARISH_MAX else "bullish" if score >= BULLISH_MIN else "neutral"
    return {"score": score, "label": label, "reasons": reasons, "htf_pts": h_pts, "ltf_pts": l_pts, "bonus": bonus}


def build_structure(ltf_interval: str, ltf_candles: list[dict], htf_candles: list[dict]) -> dict:
    """API 응답의 structure dict (스펙 11절). ltf_candles는 비어 있지 않아야 한다."""
    htf_interval = HTF_OF[ltf_interval]
    htf = structure_state(htf_candles)
    ltf = structure_state(ltf_candles)
    scored = score_structure(htf, ltf, htf_interval, ltf_interval)
    return {"htf_interval": htf_interval, "htf": htf, "ltf": ltf, **scored}
