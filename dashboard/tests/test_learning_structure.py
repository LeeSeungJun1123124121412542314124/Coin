"""HTF-LTF 구조 점수·구조 범위 테스트 (순수 함수, DB 없음)."""

import pytest

from dashboard.backend.services import learning_structure as ls

STEP = 60_000


def _bar(i, h, low, c):
    return {"open_time": i * STEP, "open": c, "high": h, "low": low, "close": c, "volume": 1.0}


def _bars(specs):
    """(high, low, close) 튜플 리스트 -> 캔들."""
    return [_bar(i, *s) for i, s in enumerate(specs)]


def _wick(peaks):
    """골(고가 5.5·저가 5·종가 5)과 봉우리(고가=peak, 종가 5)를 번갈아 놓은 캔들.

    종가가 늘 5라서 돌파가 생기지 않고, 저가가 모두 같아서 저점 스윙도 없다.
    마지막에 골 1개를 붙여 마지막 봉우리가 확정되게 한다.
    """
    specs = []
    for p in peaks:
        specs += [(5.5, 5.0, 5.0), (p, 5.0, 5.0)]
    specs.append((5.5, 5.0, 5.0))
    return _bars(specs)


def _zig(vals, shift=0.0):
    """각 값 v를 고가 v+1·저가 v-1·종가 v 캔들로."""
    return _bars([(v + 1 + shift, v - 1 + shift, v + shift) for v in vals])


def _prices(items):
    return [s["price"] for s in items]


# 1. 스윙 ---------------------------------------------------------------

def test_swings_short_mid_long_high():
    sw = ls.swings(_wick([10, 12, 11, 15, 12, 14, 11]))
    assert _prices(sw["short_high"]) == [10, 12, 11, 15, 12, 14, 11]
    assert _prices(sw["mid_high"]) == [12, 15, 14]
    assert _prices(sw["long_high"]) == [15]


def test_swings_low_mirror_of_high():
    neg = [
        {**c, "high": -c["low"], "low": -c["high"], "open": -c["open"], "close": -c["close"]}
        for c in _wick([10, 12, 11, 15, 12, 14, 11])
    ]
    sw = ls.swings(neg)
    assert _prices(sw["mid_low"]) == [-12, -15, -14]
    assert _prices(sw["long_low"]) == [-15]


def test_equal_values_are_not_swings():
    assert ls.swings(_wick([10, 10, 10]))["mid_high"] == []


def test_swing_confirmed_after_right_bar():
    sw = ls.swings(_wick([10, 12, 11]))
    assert sw["mid_high"] == [{"idx": 3, "price": 12, "confirm": 6}]  # 오른쪽 이웃 스윙(5번 봉)이 6번 봉에서 확정


# 2. 돌파 ---------------------------------------------------------------

def _base_up():
    """중기 고점 12(3번 봉)가 확정된 캔들 7개."""
    return _wick([10, 12, 11])


def test_wick_over_mid_high_is_not_break():
    wick_only = _base_up() + [_bar(7, 13, 5, 5)]
    assert ls.structure_breaks(wick_only) == []


def test_close_over_mid_high_is_weak_break():
    candles = _base_up() + [_bar(7, 13, 5, 5), _bar(8, 13, 5, 12.5)]
    assert ls.structure_breaks(candles) == [
        {"idx": 8, "time": 8 * STEP, "level": 12, "direction": "up", "kind": "bos", "strength": "weak"}
    ]


def test_close_over_long_high_is_strong_break():
    base = _wick([10, 12, 11, 15, 12, 14, 11])  # 장기 고점 15, 가장 최근 안 깨진 중기 고점 14
    weak = ls.structure_breaks(base + [_bar(15, 14.5, 5, 14.5)])
    assert [(b["level"], b["strength"]) for b in weak] == [(14, "weak")]
    strong = ls.structure_breaks(base + [_bar(15, 15.5, 5, 15.5)])
    assert [(b["level"], b["strength"]) for b in strong] == [(15, "strong")]


# 3. BoS / CHoCH --------------------------------------------------------

def _first_up_break():
    """8번 봉에서 12를 종가로 넘는 약한 상승 돌파 + 이후 고가는 모두 13 이하."""
    return _base_up() + [_bar(7, 13, 5, 5), _bar(8, 13, 5, 12.5)]


def test_same_direction_break_is_bos():
    c = _first_up_break()
    # 새 봉우리 14, 16, 15(고가). 봉우리 사이 골은 13 아래, 종가는 모두 12.5
    for h in (14, 16, 15):
        c.append(_bar(len(c), 12.6, 12, 12.5))
        c.append(_bar(len(c), h, 12, 12.5))
    c.append(_bar(len(c), 12.6, 12, 12.5))
    c.append(_bar(len(c), 16.6, 12, 16.5))
    breaks = ls.structure_breaks(c)
    assert [(b["direction"], b["kind"], b["level"]) for b in breaks] == [("up", "bos", 12), ("up", "bos", 16)]


def test_opposite_direction_break_is_choch():
    c = _first_up_break()
    # 저점 10, 9, 10.5 (사이사이 저가 12인 평범한 봉) 뒤 종가 8.5로 중기 저점 9 이탈
    for low in (10, 9, 10.5):
        c.append(_bar(len(c), 13, 12, 12.5))
        c.append(_bar(len(c), 13, low, 12.5))
    c.append(_bar(len(c), 13, 12, 12.5))
    c.append(_bar(len(c), 13, 8.5, 8.5))
    breaks = ls.structure_breaks(c)
    assert [(b["direction"], b["kind"], b["level"]) for b in breaks] == [("up", "bos", 12), ("down", "choch", 9)]


# 7. 자료 부족 + 상태 -----------------------------------------------------

def test_fewer_than_60_candles_is_insufficient():
    s = ls.structure_state(_zig([100 + i % 5 for i in range(59)]))
    assert s == {"trend": "neutral", "fresh": False, "insufficient": True, "last_break": None,
                 "range": {"high": None, "low": None}}


def test_state_without_break_is_neutral():
    flat = _bars([(100.0, 100.0, 100.0)] * 60)
    assert ls.structure_state(flat) == {"trend": "neutral", "fresh": False, "insufficient": False,
                                        "last_break": None, "range": {"high": None, "low": None}}


def _rising(pairs=35):
    """고점이 오르내리며 올라가는 캔들 — 상승 돌파가 계속 생긴다."""
    vals = []
    for k in range(pairs):
        peak = 110 + 4 * k + (6 if k % 2 else 0)
        vals += [peak - 15, peak]
    vals.append(vals[-2])
    return _zig(vals)


def test_state_fresh_up_trend():
    s = ls.structure_state(_rising())
    assert s["trend"] == "up" and s["fresh"] is True and s["insufficient"] is False
    assert s["last_break"]["direction"] == "up"
    assert set(s["last_break"]) == {"time", "level", "direction", "kind", "strength", "bars_ago"}
    assert set(s["range"]) == {"high", "low"}


def test_state_stale_when_break_older_than_20_bars():
    base = _rising()
    last = base[-1]["close"]
    c = base + [_bar(len(base) + i, last, last, last) for i in range(25)]
    s = ls.structure_state(c)
    assert s["trend"] == "up" and s["fresh"] is False and s["last_break"]["bars_ago"] > 20


# 4. 점수 ---------------------------------------------------------------

def _st(trend, fresh):
    if trend == "neutral":
        return {"trend": "neutral", "fresh": False, "insufficient": False, "last_break": None}
    lb = {"time": 0, "level": 1.0, "direction": trend, "kind": "choch", "strength": "weak",
          "bars_ago": 3 if fresh else 23}
    return {"trend": trend, "fresh": fresh, "insufficient": False, "last_break": lb,
            "range": {"high": None, "low": None}}


@pytest.mark.parametrize("htf,ltf,score,label", [
    (_st("up", False), _st("down", True), 35, "bearish"),
    (_st("neutral", False), _st("up", True), 70, "bullish"),
    (_st("up", True), _st("up", True), 100, "bullish"),
    (_st("neutral", False), _st("neutral", False), 50, "neutral"),
    (_st("down", True), _st("down", True), 0, "bearish"),
])
def test_score_table(htf, ltf, score, label):
    r = ls.score_structure(htf, ltf, "1d", "4h")
    assert (r["score"], r["label"]) == (score, label)


def test_score_label_boundaries():
    # HTF 오래됨 상승(+5) + LTF 오래됨 하락(-10) = 45 -> neutral, HTF 신선 하락(-20)+LTF 오래됨 하락(-10) = 20
    assert ls.score_structure(_st("up", False), _st("down", False), "1d", "1h")["label"] == "neutral"
    assert ls.score_structure(_st("down", True), _st("neutral", False), "1d", "1h")["score"] == 30


def test_score_reasons_korean():
    r = ls.score_structure(_st("up", False), _st("down", True), "1d", "4h")
    assert r["reasons"] == [
        "일봉: 상승 전환(CHoCH, 약), 마지막 돌파 23봉 전(오래됨) +5",
        "4시간봉: 하락 전환(CHoCH, 약), 마지막 돌파 3봉 전(신선) -20",
    ]


def test_score_monthly_has_no_htf():
    r = ls.score_structure(ls.structure_state([]), _st("up", True), ls.HTF_OF["1M"], "1M")
    assert r["score"] == 70 and r["reasons"][0] == "월봉: 상위 시간봉 없음, 중립 0"


def test_htf_mapping():
    assert ls.HTF_OF == {"1h": "1d", "4h": "1d", "1d": "1w", "1w": "1M", "1M": None}


# 11절: 구조 범위 · 기여 점수 · build_structure ----------------------------

def _live_levels(candles):
    """structure_breaks와 같은 규칙으로 마지막 봉 시점의 안 깨진 가장 최근 중기 고점/저점을 독립 계산."""
    sw = ls.swings(candles)
    last = len(candles) - 1
    out = {}
    for key, beat in (("mid_high", lambda cl, lv: cl > lv), ("mid_low", lambda cl, lv: cl < lv)):
        live = [s for s in sw[key] if s["confirm"] <= last
                and not any(beat(c["close"], s["price"]) for c in candles[s["confirm"]:])]
        out[key] = live[-1]["price"] if live else None
    return out


def test_range_matches_levels_used_by_break_detection():
    # 돌파 전: 중기 고점 12가 범위의 high
    pre = _base_up() + [_bar(7, 13, 5, 5)] * 53
    s = ls.structure_state(pre)
    assert s["range"]["high"] == 12 == _live_levels(pre)["mid_high"]
    rising = _rising()
    r = ls.structure_state(rising)["range"]
    live = _live_levels(rising)
    assert (r["high"], r["low"]) == (live["mid_high"], live["mid_low"])


def test_broken_level_leaves_range():
    pre = _base_up() + [_bar(7, 13, 5, 5)] * 53
    assert ls.structure_state(pre)["range"]["high"] == 12
    broken = pre + [_bar(len(pre), 13, 5, 12.5)]
    assert ls.structure_state(broken)["range"]["high"] is None  # 12는 종가로 깨졌고 다른 중기 고점은 없다


def test_score_parts_sum_to_score():
    for htf, ltf in ((_st("up", False), _st("down", True)), (_st("up", True), _st("up", True)),
                     (_st("neutral", False), _st("up", True)), (_st("down", True), _st("down", False))):
        r = ls.score_structure(htf, ltf, "1d", "4h")
        assert r["score"] == 50 + r["htf_pts"] + r["ltf_pts"] + r["bonus"]
    both = ls.score_structure(_st("up", True), _st("up", True), "1d", "4h")
    assert (both["htf_pts"], both["ltf_pts"], both["bonus"]) == (20, 20, 10)  # 합계는 100으로 잘리지 않는 경우만 검증
    assert ls.score_structure(_st("up", False), _st("down", True), "1d", "4h")["bonus"] == 0


def test_build_structure_shape_and_insufficient_range():
    flat = _bars([(100.0, 100.0, 100.0)] * 59)
    s = ls.build_structure("1d", flat, flat)
    assert set(s) == {"htf_interval", "htf", "ltf", "score", "label", "reasons", "htf_pts", "ltf_pts", "bonus"}
    assert s["htf_interval"] == "1w"
    assert s["htf"]["range"] == s["ltf"]["range"] == {"high": None, "low": None}
    m = ls.build_structure("1M", _rising(), [])
    assert m["htf_interval"] is None and m["htf_pts"] == 0 and m["ltf"]["trend"] == "up"
