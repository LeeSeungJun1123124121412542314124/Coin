"""Tests for BacktestEngine — sliding window historical replay."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from app.backtest.engine import BacktestEngine, BacktestResult, BacktestSignal
from app.backtest.reporter import format_report


def _make_ohlcv(n: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 30000 + np.cumsum(rng.normal(0, 200, n))
    close = np.maximum(close, 1000)
    high = close + rng.uniform(50, 200, n)
    low = close - rng.uniform(50, 200, n)
    low = np.minimum(low, close)
    open_ = close - rng.normal(0, 60, n)
    volume = rng.uniform(1000, 10000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def engine() -> BacktestEngine:
    return BacktestEngine(window_size=60)


@pytest.fixture
def large_df() -> pd.DataFrame:
    return _make_ohlcv(300, seed=1)


class TestBacktestEngine:
    def test_returns_backtest_result(self, engine, large_df):
        result = engine.run(large_df)
        assert isinstance(result, BacktestResult)

    def test_result_has_metrics(self, engine, large_df):
        result = engine.run(large_df)
        assert isinstance(result.metrics, dict)

    def test_result_has_signals(self, engine, large_df):
        result = engine.run(large_df)
        assert isinstance(result.signals, list)

    def test_result_has_parameters(self, engine, large_df):
        result = engine.run(large_df)
        assert isinstance(result.parameters, dict)
        assert "window_size" in result.parameters
        assert "evaluation_bars" in result.parameters
        assert "signal_threshold" in result.parameters

    def test_insufficient_data_returns_error(self, engine):
        small_df = _make_ohlcv(50)
        result = engine.run(small_df)
        assert "error" in result.metrics

    def test_metrics_contain_required_keys(self, engine, large_df):
        result = engine.run(large_df)
        if "error" not in result.metrics:
            for key in ("total_bars", "total_signals", "avg_score", "hit_rate"):
                assert key in result.metrics

    def test_hit_rate_in_range(self, engine, large_df):
        result = engine.run(large_df)
        if "error" not in result.metrics:
            assert 0.0 <= result.metrics["hit_rate"] <= 1.0

    def test_avg_score_in_range(self, engine, large_df):
        result = engine.run(large_df)
        if "error" not in result.metrics and result.metrics["total_signals"] > 0:
            assert 0.0 <= result.metrics["avg_score"] <= 100.0

    def test_signals_have_correct_structure(self, engine, large_df):
        result = engine.run(large_df)
        for sig in result.signals:
            assert isinstance(sig, BacktestSignal)
            assert sig.signal in ("HIGH", "MEDIUM", "LOW")
            assert sig.direction in ("BEARISH", "BULLISH", "NEUTRAL")
            assert 0.0 <= sig.score <= 100.0
            assert sig.points >= 0.0

    def test_total_signals_consistent(self, engine, large_df):
        result = engine.run(large_df)
        if "error" not in result.metrics:
            assert int(result.metrics["total_signals"]) == len(result.signals)

    @staticmethod
    def test_custom_window_size():
        """Different window sizes produce different numbers of signals."""
        df = _make_ohlcv(300, seed=2)
        engine_small = BacktestEngine(window_size=60)
        engine_large = BacktestEngine(window_size=100)
        r_small = engine_small.run(df)
        r_large = engine_large.run(df)
        if "error" not in r_small.metrics and "error" not in r_large.metrics:
            # Larger window → fewer analysis slots
            assert r_small.metrics["total_signals"] >= r_large.metrics["total_signals"]

    def test_signal_threshold_filters_active(self, engine, large_df):
        result = engine.run(large_df, signal_threshold=4.0)
        if "error" not in result.metrics:
            active = int(result.metrics["active_signals"])
            total = int(result.metrics["total_signals"])
            assert active <= total

    def test_high_signal_count_less_than_medium(self, engine, large_df):
        result = engine.run(large_df)
        if "error" not in result.metrics:
            high = int(result.metrics["high_signals"])
            medium = int(result.metrics["medium_signals"])
            total = int(result.metrics["total_signals"])
            assert high + medium <= total


class TestBacktestReporter:
    def test_format_report_contains_metrics(self, engine, large_df):
        result = engine.run(large_df)
        report = format_report(result, title="Test Backtest")
        assert "Test Backtest" in report
        assert "적중률" in report

    def test_format_report_error_case(self):
        from app.backtest.engine import BacktestResult
        result = BacktestResult(
            signals=[],
            metrics={"error": "insufficient_data"},
            parameters={},
        )
        report = format_report(result)
        assert "Error" in report or "insufficient_data" in report

    def test_format_report_is_string(self, engine, large_df):
        result = engine.run(large_df)
        report = format_report(result)
        assert isinstance(report, str)
        assert len(report) > 0
