"""와이코프 후보(스프링/업스러스트) 판정 테스트."""

from dashboard.backend.services.learning_indicators import wyckoff_candidates

STEP = 60_000


def _box(hi=110.0, lo=100.0, close=105.0, n=30, vol=100.0):
    """n봉짜리 박스 구간 캔들."""
    return [
        {"open_time": i * STEP, "open": close, "high": hi, "low": lo, "close": close, "volume": vol}
        for i in range(n)
    ]


def _with_bar(box, high, low, close, vol):
    """박스 뒤에 테스트 봉 1개를 붙인 독립 시퀀스."""
    bar = {"open_time": len(box) * STEP, "open": close, "high": high, "low": low, "close": close, "volume": vol}
    return box + [bar]


def test_spring_strong():
    r = wyckoff_candidates(_with_bar(_box(), 106, 95, 105, 300.0))
    assert r["volume_spikes"] == [30 * STEP]
    assert r["candidates"] == [
        {"time": 30 * STEP, "type": "spring", "strong": True, "box_high": 110.0, "box_low": 100.0}
    ]
    assert r["current_box"] == {"high": 110.0, "low": 100.0, "start": 0, "end": 29 * STEP}


def test_upthrust_not_strong():
    r = wyckoff_candidates(_with_bar(_box(), 115, 107, 108, 100.0))
    assert r["volume_spikes"] == []
    assert [(c["type"], c["strong"]) for c in r["candidates"]] == [("upthrust", False)]


def test_close_below_box_is_not_candidate():
    r = wyckoff_candidates(_with_bar(_box(), 100, 95, 94, 100.0))
    assert r["candidates"] == []


def test_wide_box_has_no_candidate():
    box = _box(hi=115.0, lo=85.0, close=100.0)  # 폭 30%
    r = wyckoff_candidates(_with_bar(box, 101, 80, 100, 100.0))
    assert r["candidates"] == []
    assert r["current_box"] is None


def test_width_pct_recalculation():
    box = _box(hi=115.0, lo=85.0, close=100.0)
    r = wyckoff_candidates(_with_bar(box, 101, 80, 100, 100.0), width_pct=40)
    assert [c["type"] for c in r["candidates"]] == ["spring"]


def test_vol_mult_recalculation():
    candles = _with_bar(_box(), 106, 95, 105, 300.0)
    assert wyckoff_candidates(candles, vol_mult=4)["candidates"][0]["strong"] is False


def test_not_enough_bars():
    r = wyckoff_candidates(_box(n=30))
    assert r == {"volume_spikes": [], "candidates": [], "current_box": None}


def test_both_sides_breakout_yields_both_candidates():
    r = wyckoff_candidates(_with_bar(_box(), 115, 95, 105, 100.0))
    assert len(r["candidates"]) == 2
    assert {c["type"] for c in r["candidates"]} == {"spring", "upthrust"}
