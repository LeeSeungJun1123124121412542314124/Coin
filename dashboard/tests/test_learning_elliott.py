"""엘리엇 학습용 지그재그 피벗·피보나치 레벨 테스트."""

import pytest

from dashboard.backend.services import learning_indicators as li


def _bars(prices):
    """경로의 각 점을 open=high=low=close=price인 1봉으로 만든다."""
    return [
        {"open_time": i * 1000, "open": p, "high": p, "low": p, "close": p, "volume": 1.0}
        for i, p in enumerate(prices)
    ]


def _as_tuples(pivots):
    return [(p["kind"], p["price"]) for p in pivots]


def test_zigzag_threshold_10pct():
    pivots = li.zigzag(_bars([100, 120, 108, 130]), 10)
    assert _as_tuples(pivots) == [("low", 100), ("high", 120), ("low", 108)]
    assert [p["time"] for p in pivots] == [0, 1000, 2000]


def test_zigzag_same_path_recalculates_with_threshold():
    path = [100, 120, 108, 116, 113, 130]
    p10 = li.zigzag(_bars(path), 10)
    assert _as_tuples(p10) == [("low", 100), ("high", 120), ("low", 108)]
    p2 = li.zigzag(_bars(path), 2)
    assert _as_tuples(p2) == [("low", 100), ("high", 120), ("low", 108), ("high", 116), ("low", 113)]


def test_zigzag_empty_and_single():
    assert li.zigzag([], 10) == []
    assert li.zigzag(_bars([100]), 10) == []


def test_zigzag_no_wave_field():
    for p in li.zigzag(_bars([100, 120, 108, 130]), 10):
        assert "wave" not in p


def test_fib_levels():
    pivots = [{"time": 0, "price": 100, "kind": "low"}, {"time": 1, "price": 120, "kind": "high"}]
    out = li.fib_levels(pivots, [0.382, 0.5, 0.618, 1.0, 1.618])
    assert [o["price"] for o in out] == pytest.approx([112.36, 110, 107.64, 100, 87.64])
    assert [o["level"] for o in out] == [0.382, 0.5, 0.618, 1.0, 1.618]
    assert all("wave" not in o for o in out)
    assert li.fib_levels(pivots[:1], [0.5]) == []
