"""Tests for OnchainAnalyzer — 7 tests."""

from __future__ import annotations

import pytest

from app.analyzers.onchain_analyzer import OnchainAnalyzer, OnchainDataUnavailableError


@pytest.fixture
def analyzer() -> OnchainAnalyzer:
    return OnchainAnalyzer()


def _data(inflow: float, outflow: float, whale_volume: float = 0.0, dormant: bool = False) -> dict:
    return {
        "exchange_inflow": inflow,
        "exchange_outflow": outflow,
        "whale_transaction_volume": whale_volume,
        "dormant_whale_activated": dormant,
    }


class TestOnchainAnalyzer:
    def test_high_inflow_signals_sell_pressure(self, analyzer):
        data = _data(inflow=1000, outflow=500)
        result = analyzer.analyze(data)
        assert result.signal == "HIGH_SELL_PRESSURE"
        assert result.score >= 70

    def test_high_outflow_signals_accumulation(self, analyzer):
        data = _data(inflow=500, outflow=1000)
        result = analyzer.analyze(data)
        assert result.signal == "ACCUMULATION"
        assert result.score <= 35

    def test_balanced_flow_is_neutral(self, analyzer):
        data = _data(inflow=1000, outflow=1000)
        result = analyzer.analyze(data)
        assert result.signal == "NEUTRAL"
        assert 30 <= result.score <= 70

    def test_whale_boost_on_large_transaction(self, analyzer):
        data_no_whale = _data(inflow=1000, outflow=1000, whale_volume=0)
        data_whale = _data(inflow=1000, outflow=1000, whale_volume=100)
        score_no_whale = analyzer.analyze(data_no_whale).score
        score_whale = analyzer.analyze(data_whale).score
        assert score_whale > score_no_whale

    def test_dormant_whale_sets_alert_flag(self, analyzer):
        data = _data(inflow=1000, outflow=1000, whale_volume=0, dormant=True)
        result = analyzer.analyze(data)
        assert result.details.get("whale_alert") is True

    def test_none_data_raises_error(self, analyzer):
        with pytest.raises(OnchainDataUnavailableError):
            analyzer.analyze(None)

    def test_returns_analysis_result_type(self, analyzer):
        from app.analyzers.base import AnalysisResult

        data = _data(inflow=800, outflow=600)
        result = analyzer.analyze(data)
        assert isinstance(result, AnalysisResult)
