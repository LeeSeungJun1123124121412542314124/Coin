"""국면 자동 판정 순수 함수 테스트."""

from __future__ import annotations

import pytest

from dashboard.backend.services.learning_review import HORIZONS, JUDGE_PCT, judge_phase


def test_constants():
    assert HORIZONS == (14, 28)
    assert JUDGE_PCT == 5.0


@pytest.mark.parametrize("phase,close,expected", [
    ("markup", 105, "hit"), ("markup", 104.99, "partial"), ("markup", 95, "miss"),
    ("accumulation", 95.01, "partial"), ("accumulation", 105, "hit"), ("accumulation", 95, "miss"),
    ("distribution", 95, "hit"), ("distribution", 105, "miss"), ("distribution", 100, "partial"),
    ("markdown", 105, "miss"), ("markdown", 95, "hit"),
    ("unclear", 130, None)])
def test_judge_phase(phase, close, expected):
    assert judge_phase(phase, 100.0, close) == expected


def test_judge_phase_custom_pct():
    assert judge_phase("markup", 100.0, 102.0, pct=2.0) == "hit"
