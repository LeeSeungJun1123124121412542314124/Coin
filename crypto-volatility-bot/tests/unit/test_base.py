"""BaseAnalyzer._normalize / _clamp — NaN 안전성 테스트.

버그: max/min은 NaN을 통과시켜 _clamp(NaN)이 상한(100)을 반환 →
     워밍업 미달 지표(NaN)가 만점으로 둔갑, 오탐 유발.
"""
from __future__ import annotations

import math

from app.analyzers.base import AnalysisResult, BaseAnalyzer


class _Dummy(BaseAnalyzer):
    def analyze(self, data):  # 추상 메서드 충족용
        return AnalysisResult(score=0.0, signal="NEUTRAL")


def test_normalize_nan_returns_neutral():
    """NaN 입력은 중립(50) — 상한(100)으로 둔갑 금지."""
    assert _Dummy()._normalize(float("nan"), 0.0, 100.0) == 50.0


def test_clamp_nan_returns_neutral():
    d = _Dummy()
    result = d._clamp(float("nan"))
    assert not math.isnan(result)
    assert result == 50.0


def test_normalize_normal_values_unchanged():
    d = _Dummy()
    assert d._normalize(50.0, 0.0, 100.0) == 50.0
    assert d._normalize(0.0, 0.0, 100.0) == 0.0
    assert d._normalize(100.0, 0.0, 100.0) == 100.0
    assert d._normalize(150.0, 0.0, 100.0) == 100.0  # 상한 클램프
