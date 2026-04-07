"""Tests for SentimentAnalyzer — 9 tests."""

from __future__ import annotations

import pytest

from app.analyzers.sentiment_analyzer import SentimentAnalyzer


@pytest.fixture
def analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer()


class TestSentimentAnalyzer:
    def test_extreme_fear_has_boost(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 10})
        assert result.details.get("volatility_boost", 0) > 0
        assert result.score > 50

    def test_extreme_greed_has_boost(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 90})
        assert result.details.get("volatility_boost", 0) > 0
        assert result.score > 50

    def test_neutral_fg_no_boost(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 50})
        assert result.details.get("volatility_boost", 0) == pytest.approx(0.0)
        assert result.score == pytest.approx(50.0)

    def test_boundary_25_no_boost(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 25})
        assert result.details.get("volatility_boost", 0) == pytest.approx(0.0)

    def test_boundary_75_no_boost(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 75})
        assert result.details.get("volatility_boost", 0) == pytest.approx(0.0)

    def test_boost_formula(self, analyzer):
        fg = 10
        result = analyzer.analyze({"fear_greed_index": fg})
        expected_boost = abs(50 - fg) * 0.5
        assert result.details["volatility_boost"] == pytest.approx(expected_boost)

    def test_score_clamped_at_100(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 0})
        assert result.score <= 100

    def test_none_data_returns_neutral(self, analyzer):
        result = analyzer.analyze(None)
        assert result.score == pytest.approx(50.0)

    def test_signal_extreme_fear(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 10})
        assert result.signal == "EXTREME_FEAR"

    def test_signal_extreme_greed(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 90})
        assert result.signal == "EXTREME_GREED"

    def test_signal_neutral(self, analyzer):
        result = analyzer.analyze({"fear_greed_index": 50})
        assert result.signal == "NEUTRAL"
