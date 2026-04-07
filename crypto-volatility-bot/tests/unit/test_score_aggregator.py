"""Tests for ScoreAggregator — 9 tests."""

from __future__ import annotations

import pytest

from app.analyzers.base import AnalysisResult
from app.analyzers.score_aggregator import AggregatedResult, ScoreAggregator

_WEIGHTS = {"onchain": 0.40, "technical": 0.35, "sentiment": 0.25}


@pytest.fixture
def aggregator() -> ScoreAggregator:
    return ScoreAggregator(weights=_WEIGHTS)


def _result(score: float, whale_alert: bool = False) -> AnalysisResult:
    return AnalysisResult(
        score=score,
        signal="TEST",
        details={"whale_alert": whale_alert},
    )


class TestScoreAggregator:
    def test_weighted_score_calculation(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(80),
            technical=_result(60),
            sentiment=_result(40),
        )
        expected = 80 * 0.40 + 60 * 0.35 + 40 * 0.25
        assert result.final_score == pytest.approx(expected)

    def test_weighted_score_exact_value(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(80),
            technical=_result(60),
            sentiment=_result(40),
        )
        assert result.final_score == pytest.approx(63.0)

    def test_score_clamped_at_100(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(100),
            technical=_result(100),
            sentiment=_result(100),
        )
        assert result.final_score <= 100

    def test_score_clamped_at_0(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(0),
            technical=_result(0),
            sentiment=_result(0),
        )
        assert result.final_score >= 0

    def test_alert_level_emergency(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(100), technical=_result(100), sentiment=_result(100)
        )
        assert result.alert_level == "EMERGENCY"

    def test_alert_level_high(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(79), technical=_result(79), sentiment=_result(79)
        )
        assert result.alert_level == "HIGH"

    def test_alert_level_medium(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(50), technical=_result(50), sentiment=_result(50)
        )
        assert result.alert_level == "MEDIUM"

    def test_alert_level_low(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(30), technical=_result(30), sentiment=_result(30)
        )
        assert result.alert_level == "LOW"

    def test_whale_alert_propagated(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(50, whale_alert=True),
            technical=_result(50),
            sentiment=_result(50),
        )
        assert result.whale_alert is True

    def test_returns_aggregated_result_type(self, aggregator):
        result = aggregator.aggregate(
            onchain=_result(50),
            technical=_result(50),
            sentiment=_result(50),
        )
        assert isinstance(result, AggregatedResult)

    def test_alert_score_equals_technical_score(self, aggregator):
        # 긴급 알림용 alert_score는 기술적 점수 100%
        result = aggregator.aggregate(
            onchain=_result(80),
            technical=_result(65),
            sentiment=_result(40),
        )
        assert result.alert_score == pytest.approx(65.0)

    def test_alert_score_independent_of_onchain_and_sentiment(self, aggregator):
        # 온체인/감성이 아무리 높아도 alert_score는 기술적 점수만 반영
        result = aggregator.aggregate(
            onchain=_result(100),
            technical=_result(30),
            sentiment=_result(100),
        )
        assert result.alert_score == pytest.approx(30.0)

    def test_boundary_79_is_high_not_emergency(self, aggregator):
        # Score exactly 79 should be HIGH
        score = 79
        result = aggregator.aggregate(
            onchain=_result(score), technical=_result(score), sentiment=_result(score)
        )
        assert result.alert_level == "HIGH"

    def test_boundary_80_is_emergency(self, aggregator):
        # Score exactly 80 should be EMERGENCY
        score = 80
        result = aggregator.aggregate(
            onchain=_result(score), technical=_result(score), sentiment=_result(score)
        )
        assert result.alert_level == "EMERGENCY"
