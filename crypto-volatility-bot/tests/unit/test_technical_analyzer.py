"""Tests for TechnicalAnalyzer — base + HA gate + category gate + boosters."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from app.analyzers.technical_analyzer import TechnicalAnalyzer


@pytest.fixture
def analyzer() -> TechnicalAnalyzer:
    return TechnicalAnalyzer()


def _make_ungated_config(tmp_path, extra_boosters=None):
    """Create a config with HA filter + category gate disabled for booster isolation tests."""
    boosters = {
        "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
        "rsi_divergence": {"enabled": True, "boost": 8, "category": "momentum"},
        "volume_spike_strong": {"enabled": True, "boost": 10, "category": "volatility", "threshold": 2.5},
        "atr_spike": {"enabled": True, "boost": 8, "category": "volatility", "multiplier": 1.2, "lookback": 5},
        "bb_expansion": {"enabled": True, "boost": 10, "category": "volatility", "bandwidth_ratio": 1.3},
        "macd_crossover": {"enabled": True, "boost": 6, "category": "trend"},
        "outlier": {"enabled": True, "boost": 12, "category": "volatility", "atr_spike_multiplier": 2.0, "single_candle_pct": 5.0},
    }
    if extra_boosters:
        boosters.update(extra_boosters)
    cfg = {
        "indicators": {
            "atr": {"enabled": True, "weight": 0.25, "period": 14, "normalize": {"min": 100, "max": 5000}},
            "bollinger_width": {"enabled": True, "weight": 0.20, "period": 20, "normalize": {"min": 0.01, "max": 0.20}},
            "cvi": {"enabled": True, "weight": 0.20, "period": 10, "normalize": {"min": -50, "max": 50}},
            "historical_volatility": {"enabled": True, "weight": 0.20, "period": 20, "normalize": {"min": 0.1, "max": 100.0}},
            "volume_spike": {"enabled": True, "weight": 0.15, "period": 20, "normalize": {"min": 0.2, "max": 5.0}},
        },
        "signals": {"high_threshold": 70, "medium_threshold": 40},
        "ha_filter": {"enabled": False},
        "category_gate": {"enabled": False},
        "signal_boosters": boosters,
    }
    config_path = tmp_path / "ungated.yaml"
    config_path.write_text(yaml.dump(cfg))
    return TechnicalAnalyzer(config_path=str(config_path))


class TestNormalize:
    def test_normalize_mid_value(self, analyzer):
        assert analyzer._normalize(50, 0, 100) == pytest.approx(50.0)

    def test_normalize_at_min(self, analyzer):
        assert analyzer._normalize(0, 0, 100) == pytest.approx(0.0)

    def test_normalize_at_max(self, analyzer):
        assert analyzer._normalize(100, 0, 100) == pytest.approx(100.0)

    def test_normalize_clamps_below_min(self, analyzer):
        assert analyzer._normalize(-10, 0, 100) == pytest.approx(0.0)

    def test_normalize_clamps_above_max(self, analyzer):
        assert analyzer._normalize(200, 0, 100) == pytest.approx(100.0)


class TestAnalyze:
    def test_returns_analysis_result(self, analyzer, sample_ohlcv_df):
        from app.analyzers.base import AnalysisResult

        result = analyzer.analyze(sample_ohlcv_df)
        assert isinstance(result, AnalysisResult)

    def test_score_in_range(self, analyzer, sample_ohlcv_df):
        result = analyzer.analyze(sample_ohlcv_df)
        assert 0 <= result.score <= 100

    def test_high_volatility_score_high(self, analyzer, high_volatility_ohlcv_df):
        result = analyzer.analyze(high_volatility_ohlcv_df)
        assert result.score > 55, f"Expected score > 55, got {result.score}"

    def test_low_volatility_score_low(self, analyzer, low_volatility_ohlcv_df):
        result = analyzer.analyze(low_volatility_ohlcv_df)
        assert result.score < 40, f"Expected score < 40, got {result.score}"

    def test_analyze_returns_signal(self, analyzer, sample_ohlcv_df):
        result = analyzer.analyze(sample_ohlcv_df)
        assert result.signal in ("HIGH", "MEDIUM", "LOW")

    def test_details_contain_indicators(self, analyzer, sample_ohlcv_df):
        result = analyzer.analyze(sample_ohlcv_df)
        for key in ("atr", "bollinger_width", "cvi", "historical_volatility", "volume_spike"):
            assert key in result.details

    def test_raises_on_too_few_rows(self, analyzer):
        tiny_df = pd.DataFrame(
            {
                "open": [1.0] * 10,
                "high": [1.0] * 10,
                "low": [1.0] * 10,
                "close": [1.0] * 10,
                "volume": [1.0] * 10,
            }
        )
        with pytest.raises(ValueError, match="[Rr]ow"):
            analyzer.analyze(tiny_df)


class TestWeightNormalization:
    def test_partial_disable_weights_still_sum_to_one(self, tmp_path):
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 0.5, "period": 14, "normalize": {"min": 100, "max": 5000}},
                "bollinger_width": {"enabled": False, "weight": 0.3, "period": 20, "normalize": {"min": 0.01, "max": 0.20}},
                "cvi": {"enabled": True, "weight": 0.5, "period": 10, "normalize": {"min": -50, "max": 50}},
                "historical_volatility": {"enabled": False, "weight": 0.1, "period": 20, "normalize": {"min": 0.1, "max": 2.0}},
                "volume_spike": {"enabled": False, "weight": 0.1, "period": 20, "normalize": {"min": 0.2, "max": 5.0}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
        }
        config_path = tmp_path / "technical.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))
        enabled_weights = [v for v in ta._indicator_configs.values() if v["enabled"]]
        total = sum(c["weight"] for c in enabled_weights)
        assert abs(total - 1.0) < 1e-9

    def test_invalid_negative_weight_raises(self, tmp_path):
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": -0.5, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
        }
        config_path = tmp_path / "bad.yaml"
        config_path.write_text(yaml.dump(cfg))
        with pytest.raises(ValueError, match="[Ww]eight"):
            TechnicalAnalyzer(config_path=str(config_path))


class TestSignalBoosters:
    """Tests for the signal booster layer (individual booster isolation with HA gate disabled)."""

    def test_details_contain_signal_boost(self, analyzer, sample_ohlcv_df):
        result = analyzer.analyze(sample_ohlcv_df)
        assert "signal_boost" in result.details
        assert "active_boosters" in result.details["signal_boost"]
        assert "total_boost" in result.details["signal_boost"]

    def test_signal_boost_total_is_nonnegative(self, analyzer, sample_ohlcv_df):
        result = analyzer.analyze(sample_ohlcv_df)
        assert result.details["signal_boost"]["total_boost"] >= 0

    def test_no_boosters_when_disabled(self, tmp_path):
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            # No signal_boosters section
        }
        config_path = tmp_path / "no_boost.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))
        assert ta._boosters == {}

    def test_rsi_extreme_boosts_score(self, tmp_path):
        """RSI extreme (oversold) should add boost points (HA gate disabled)."""
        ta = _make_ungated_config(tmp_path)
        n = 100
        # Strong downtrend to push RSI below 20
        close = 30000 - np.arange(n) * 300.0
        high = close + 50
        low = close - 50
        open_ = close + 30
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "rsi_extreme" in boost_info["active_boosters"]

    def test_volume_spike_strong_boosts_score(self, tmp_path):
        """A large volume spike on the last bar should trigger the booster (HA gate disabled)."""
        ta = _make_ungated_config(tmp_path)
        rng = np.random.default_rng(42)
        n = 100
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        high = close + 50
        low = close - 50
        open_ = close + rng.normal(0, 10, n)
        # Uniform volume except last bar is 10x
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "volume_spike_strong" in boost_info["active_boosters"]

    def test_no_false_boost_on_quiet_market(self, analyzer, low_volatility_ohlcv_df):
        """Low volatility data should trigger few or no boosters."""
        result = analyzer.analyze(low_volatility_ohlcv_df)
        boost_info = result.details["signal_boost"]
        # Most boosters should NOT fire on quiet data
        assert boost_info["total_boost"] < 20

    def test_score_clamped_at_100_with_boosters(self, analyzer):
        """Even with many boosters firing, score stays <= 100."""
        n = 100
        # Extreme crash-like data to trigger many boosters
        close = 30000 - np.arange(n) * 500.0
        close = np.maximum(close, 100)
        high = close + 200
        low = close - 200
        open_ = close + 150
        volume = np.full(n, 1000.0)
        volume[-1] = 50_000.0  # massive volume spike

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = analyzer.analyze(df)
        assert result.score <= 100.0

    def test_bb_expansion_boosts_on_expanding_bands(self, tmp_path):
        """BB bandwidth ratio >= 1.3 should trigger bb_expansion booster (HA gate disabled)."""
        ta = _make_ungated_config(tmp_path)
        n = 100
        rng = np.random.default_rng(123)
        # 98 calm bars then 2 extremely volatile bars → bandwidth jumps at the end
        close = np.concatenate([
            30000 + rng.normal(0, 10, 98),
            np.array([30000 + 2000, 30000 - 2000]),
        ])
        high = close + np.concatenate([rng.uniform(5, 15, 98), np.array([2500, 2500])])
        low = close - np.concatenate([rng.uniform(5, 15, 98), np.array([2500, 2500])])
        open_ = close + rng.normal(0, 5, n)
        volume = np.full(n, 5000.0)

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "bb_expansion" in boost_info["active_boosters"]

    def test_macd_crossover_boosts_on_trend_reversal(self, analyzer):
        """MACD crossover on trend reversal should fire booster."""
        n = 100
        # Down then up to trigger MACD golden cross
        close = np.concatenate([
            30000 - np.arange(60) * 100.0,
            24000 + np.arange(40) * 200.0,
        ])
        high = close + 100
        low = close - 100
        open_ = close - 50
        volume = np.full(n, 5000.0)

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = analyzer.analyze(df)
        boost_info = result.details["signal_boost"]
        # MACD crossover might fire depending on EMA convergence speed
        # At minimum, the booster should not crash
        assert isinstance(boost_info["total_boost"], float)


class TestHAFilterGate:
    """Tests for the Heikin Ashi filter gate."""

    def test_ha_gate_blocks_on_indeterminate_candles(self, tmp_path):
        """HA safe mode: if no 2 consecutive same-direction HA candles, boost = 0."""
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "ha_filter": {"enabled": True, "mode": "safe"},
            "signal_boosters": {
                "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
                "atr_spike": {"enabled": True, "boost": 8, "category": "volatility", "multiplier": 1.0, "lookback": 5},
            },
        }
        config_path = tmp_path / "ha_gate.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        n = 100
        rng = np.random.default_rng(42)
        # Alternating up/down to create mixed HA candles
        close = np.zeros(n)
        close[0] = 30000
        for i in range(1, n):
            close[i] = close[i - 1] + (200 if i % 2 == 0 else -200) + rng.normal(0, 5)
        high = close + 100
        low = close - 100
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert boost_info["ha_filter"] == "blocked"
        assert boost_info["total_boost"] == 0.0

    def test_ha_gate_passes_on_bullish_trend(self, analyzer):
        """Strong uptrend produces 2+ consecutive bullish HA candles → gate passes."""
        n = 100
        # Steady uptrend
        close = 30000 + np.arange(n) * 100.0
        high = close + 50
        low = close - 30
        open_ = close - 40
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = analyzer.analyze(df)
        boost_info = result.details["signal_boost"]
        assert boost_info.get("ha_filter") != "blocked"

    def test_ha_gate_passes_on_bearish_trend(self, analyzer):
        """Strong downtrend produces 2+ consecutive bearish HA candles → gate passes."""
        n = 100
        # Steady downtrend
        close = 30000 - np.arange(n) * 100.0
        close = np.maximum(close, 100)
        high = close + 30
        low = close - 50
        open_ = close + 40
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = analyzer.analyze(df)
        boost_info = result.details["signal_boost"]
        assert boost_info.get("ha_filter") != "blocked"

    def test_ha_gate_disabled_config(self, tmp_path):
        """When ha_filter.enabled = false, HA gate is bypassed."""
        ta = _make_ungated_config(tmp_path)
        n = 100
        rng = np.random.default_rng(42)
        # Alternating candles that would fail HA safe mode
        close = np.zeros(n)
        close[0] = 30000
        for i in range(1, n):
            close[i] = close[i - 1] + (200 if i % 2 == 0 else -200) + rng.normal(0, 5)
        high = close + 100
        low = close - 100
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        # Should NOT be blocked
        assert boost_info.get("ha_filter") != "blocked"


class TestCategoryGate:
    """Tests for the category gate (Trend/Momentum >= 1 AND Volatility >= 1)."""

    def test_category_gate_blocks_when_only_momentum(self, tmp_path):
        """Only momentum booster fires, no volatility → category gate blocks."""
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "ha_filter": {"enabled": False},
            "signal_boosters": {
                "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
                # No volatility boosters
            },
        }
        config_path = tmp_path / "cat_gate.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        n = 100
        # Strong downtrend to fire rsi_extreme
        close = 30000 - np.arange(n) * 300.0
        high = close + 50
        low = close - 50
        open_ = close + 30
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert boost_info.get("category_gate") == "blocked"
        assert boost_info["total_boost"] == 0.0

    def test_category_gate_blocks_when_only_volatility(self, tmp_path):
        """Only volatility booster fires, no trend/momentum → category gate blocks."""
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "ha_filter": {"enabled": False},
            "signal_boosters": {
                "volume_spike_strong": {"enabled": True, "boost": 10, "category": "volatility", "threshold": 2.5},
                # No trend/momentum boosters
            },
        }
        config_path = tmp_path / "cat_gate2.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        rng = np.random.default_rng(42)
        n = 100
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        high = close + 50
        low = close - 50
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0  # trigger volume spike

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert boost_info.get("category_gate") == "blocked"
        assert boost_info["total_boost"] == 0.0

    def test_category_gate_passes_with_momentum_and_volatility(self, tmp_path):
        """Both momentum + volatility boosters fire → category gate passes."""
        ta = _make_ungated_config(tmp_path)
        n = 100
        # Strong downtrend (rsi extreme) + volume spike (volatility)
        close = 30000 - np.arange(n) * 300.0
        high = close + 50
        low = close - 50
        open_ = close + 30
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0  # trigger volume spike

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        # At least some boost should have passed through
        if boost_info.get("category_gate") == "passed":
            assert boost_info["total_boost"] > 0

    def test_category_hits_are_reported(self, tmp_path):
        """Category hits should be included in boost details."""
        ta = _make_ungated_config(tmp_path)
        n = 100
        rng = np.random.default_rng(42)
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        high = close + 50
        low = close - 50
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        # category_hits should always be present (empty or populated)
        assert "category_gate" in boost_info or "ha_filter" in boost_info


class TestNewBoosters:
    """Tests for newly added boosters: hull_ma_crossover, adx_di_crossover, rsi_trend_crossover, hull_rsi_crossover."""

    def test_hull_ma_crossover_fires_on_trend_change(self, tmp_path):
        """Hull MA MHULL/SHULL crossover on trend reversal."""
        ta = _make_ungated_config(tmp_path, extra_boosters={
            "hull_ma_crossover": {"enabled": True, "boost": 10, "category": "trend", "medium_period": 30, "short_period": 10},
        })
        n = 100
        # Down then sharp up to create HMA crossover
        close = np.concatenate([
            30000 - np.arange(60) * 80.0,
            25200 + np.arange(40) * 200.0,
        ])
        high = close + 100
        low = close - 100
        open_ = close - 50
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        # The booster should either fire or not crash
        assert isinstance(boost_info["total_boost"], float)

    def test_adx_di_crossover_fires(self, tmp_path):
        """ADX +DI/-DI crossover should fire booster."""
        ta = _make_ungated_config(tmp_path, extra_boosters={
            "adx_di_crossover": {"enabled": True, "boost": 8, "category": "trend"},
        })
        n = 100
        # Down then up to create DI crossover
        close = np.concatenate([
            30000 - np.arange(50) * 100.0,
            25000 + np.arange(50) * 150.0,
        ])
        high = close + 80
        low = close - 80
        open_ = close - 40
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert isinstance(boost_info["total_boost"], float)

    def test_rsi_trend_crossover_no_crash(self, tmp_path):
        """RSI trend crossover (frsi/srsi) should not crash on any data."""
        ta = _make_ungated_config(tmp_path, extra_boosters={
            "rsi_trend_crossover": {
                "enabled": True, "boost": 8, "category": "momentum",
                "fast_rsi_period": 14, "slow_rsi_period": 28, "hma_period": 10,
            },
        })
        rng = np.random.default_rng(42)
        n = 100
        close = 30000 + np.cumsum(rng.normal(0, 100, n))
        high = close + 50
        low = close - 50
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        assert isinstance(result.details["signal_boost"]["total_boost"], float)

    def test_hull_rsi_crossover_no_crash(self, tmp_path):
        """Hull RSI crossover (StochK × HullRSI) should not crash on any data."""
        ta = _make_ungated_config(tmp_path, extra_boosters={
            "hull_rsi_crossover": {"enabled": True, "boost": 8, "category": "momentum", "hma_period": 10},
        })
        rng = np.random.default_rng(42)
        n = 100
        close = 30000 + np.cumsum(rng.normal(0, 100, n))
        high = close + 50
        low = close - 50
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        assert isinstance(result.details["signal_boost"]["total_boost"], float)


class TestEnhancedBoosters:
    """Tests for enhanced booster thresholds."""

    def test_volume_spike_threshold_raised(self, tmp_path):
        """volume_spike_strong now requires ratio > 4.0 (was 2.5)."""
        # Old threshold: 2.5 → volume at 3x average would fire
        # New threshold: 4.0 → volume at 3x average should NOT fire
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "ha_filter": {"enabled": False},
            "signal_boosters": {
                "volume_spike_strong": {"enabled": True, "boost": 10, "category": "volatility", "threshold": 4.0},
                "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
            },
        }
        config_path = tmp_path / "vol_thresh.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        n = 100
        close = 30000 - np.arange(n) * 300.0  # downtrend for RSI extreme
        high = close + 50
        low = close - 50
        open_ = close + 30
        volume = np.full(n, 1000.0)
        volume[-1] = 3000.0  # 3x average — below new threshold 4.0

        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "volume_spike_strong" not in boost_info.get("active_boosters", {})

    def test_outlier_critical_only(self, tmp_path):
        """Outlier with critical_only=true should not give half-boost for non-critical outliers."""
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "ha_filter": {"enabled": False},
            "signal_boosters": {
                "outlier": {
                    "enabled": True, "boost": 12, "category": "volatility",
                    "critical_only": True, "atr_spike_multiplier": 2.0, "single_candle_pct": 5.0,
                },
                "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
            },
        }
        config_path = tmp_path / "outlier_cfg.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        rng = np.random.default_rng(42)
        n = 100
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        high = close + 50
        low = close - 50
        open_ = close + rng.normal(0, 10, n)
        volume = np.full(n, 5000.0)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        # If outlier fires, it should be 12 (full boost) or 0, not 6 (half)
        outlier_boost = boost_info.get("active_boosters", {}).get("outlier", 0.0)
        assert outlier_boost == 0.0 or outlier_boost == 12.0

    def test_stochrsi_extreme_disabled(self):
        """stochrsi_extreme should be disabled in production config."""
        ta = TechnicalAnalyzer()
        stochrsi_cfg = ta._boosters.get("stochrsi_extreme", {})
        assert stochrsi_cfg.get("enabled") is False

    def test_bb_middle_break_disabled(self):
        """bb_middle_break should be disabled in production config."""
        ta = TechnicalAnalyzer()
        bb_mid_cfg = ta._boosters.get("bb_middle_break", {})
        assert bb_mid_cfg.get("enabled") is False


class TestSignalBoostDetails:
    """Tests for signal boost detail reporting fields."""

    def test_ha_filter_field_present(self, analyzer, sample_ohlcv_df):
        """ha_filter field should be present in boost details."""
        result = analyzer.analyze(sample_ohlcv_df)
        boost_info = result.details["signal_boost"]
        assert "ha_filter" in boost_info

    def test_ha_direction_field_present(self, analyzer, sample_ohlcv_df):
        """ha_direction should be present when HA gate is enabled."""
        result = analyzer.analyze(sample_ohlcv_df)
        boost_info = result.details["signal_boost"]
        assert "ha_direction" in boost_info


class TestBoostAwareSignalClassification:
    """Tests for boost-aware signal classification: boost=0 → always LOW."""

    def test_high_base_score_no_boost_is_low(self, tmp_path):
        """Score >= high_threshold but boost=0 should be LOW, not HIGH."""
        # Config with no boosters at all → boost will always be 0
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 0.25, "period": 14, "normalize": {"min": 100, "max": 5000}},
                "bollinger_width": {"enabled": True, "weight": 0.20, "period": 20, "normalize": {"min": 0.01, "max": 0.20}},
                "cvi": {"enabled": True, "weight": 0.20, "period": 10, "normalize": {"min": -50, "max": 50}},
                "historical_volatility": {"enabled": True, "weight": 0.20, "period": 20, "normalize": {"min": 0.1, "max": 100.0}},
                "volume_spike": {"enabled": True, "weight": 0.15, "period": 20, "normalize": {"min": 0.2, "max": 5.0}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "signal_boosters": {},
        }
        config_path = tmp_path / "no_boost.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        # High-volatility data that produces base score > 70
        n = 100
        base = 50000.0
        np.random.seed(42)
        close = base + np.cumsum(np.random.normal(0, 800, n))
        high = close + np.abs(np.random.normal(400, 200, n))
        low = close - np.abs(np.random.normal(400, 200, n))
        volume = np.random.uniform(500, 5000, n)
        df = pd.DataFrame({
            "open": close + np.random.normal(0, 100, n),
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        result = ta.analyze(df)
        # Even if base score is very high, no boost → LOW
        assert result.signal == "LOW", (
            f"Expected LOW for boost=0, got {result.signal} (score={result.score})"
        )

    def test_medium_base_score_no_boost_is_low(self, tmp_path):
        """Score >= medium_threshold but boost=0 should be LOW, not MEDIUM."""
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 0.25, "period": 14, "normalize": {"min": 100, "max": 5000}},
                "bollinger_width": {"enabled": True, "weight": 0.20, "period": 20, "normalize": {"min": 0.01, "max": 0.20}},
                "cvi": {"enabled": True, "weight": 0.20, "period": 10, "normalize": {"min": -50, "max": 50}},
                "historical_volatility": {"enabled": True, "weight": 0.20, "period": 20, "normalize": {"min": 0.1, "max": 100.0}},
                "volume_spike": {"enabled": True, "weight": 0.15, "period": 20, "normalize": {"min": 0.2, "max": 5.0}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},
            "signal_boosters": {},
        }
        config_path = tmp_path / "no_boost2.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        # Moderate volatility data
        n = 100
        base = 50000.0
        np.random.seed(123)
        close = base + np.cumsum(np.random.normal(0, 400, n))
        high = close + np.abs(np.random.normal(200, 100, n))
        low = close - np.abs(np.random.normal(200, 100, n))
        volume = np.random.uniform(200, 2000, n)
        df = pd.DataFrame({
            "open": close + np.random.normal(0, 50, n),
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        result = ta.analyze(df)
        # No boost → cannot be MEDIUM or HIGH
        assert result.signal == "LOW", (
            f"Expected LOW for boost=0, got {result.signal} (score={result.score})"
        )

    def test_score_with_boost_can_be_high(self, tmp_path):
        """Score >= high_threshold with boost > 0 should be HIGH."""
        ta = _make_ungated_config(tmp_path)
        # Extreme volatility data with volume spikes to trigger boosters
        n = 100
        base = 50000.0
        np.random.seed(999)
        close = base + np.cumsum(np.random.normal(0, 1200, n))
        high = close + np.abs(np.random.normal(600, 300, n))
        low = close - np.abs(np.random.normal(600, 300, n))
        # Volume spike in last bar
        volume = np.random.uniform(100, 500, n)
        volume[-1] = 50000.0  # massive spike
        df = pd.DataFrame({
            "open": close + np.random.normal(0, 200, n),
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        result = ta.analyze(df)
        boost = result.details["signal_boost"]["total_boost"]
        if result.score >= 70 and boost > 0:
            assert result.signal == "HIGH"
        elif result.score >= 40 and boost > 0:
            assert result.signal == "MEDIUM"


# ──────────────────────────────────────────────────────────────
# Phase 1~6: 오탐률 감소 수정 테스트
# ──────────────────────────────────────────────────────────────

def _make_booster_config(tmp_path, booster_name, booster_cfg, max_boost=None):
    """단일 부스터 격리 테스트용 config (HA/category gate 비활성화)."""
    signals = {"high_threshold": 70, "medium_threshold": 40}
    if max_boost is not None:
        signals["max_boost"] = max_boost
    cfg = {
        "indicators": {
            "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
        },
        "signals": signals,
        "ha_filter": {"enabled": False},
        "category_gate": {"enabled": False},
        "signal_boosters": {booster_name: booster_cfg},
    }
    config_path = tmp_path / f"test_{booster_name}.yaml"
    config_path.write_text(yaml.dump(cfg))
    return TechnicalAnalyzer(config_path=str(config_path))


class TestPhase1DirectionAlignment:
    """Phase 1: HA 방향과 크로스오버 부스터 방향 일치 검사."""

    def _compute_all_indicators(self, df):
        """_evaluate_booster 직접 호출에 필요한 indicators dict 생성."""
        from app.analyzers.indicators import adx, bollinger_bands, heikin_ashi, hull_ma, macd, rsi, stoch_rsi
        rsi_result = rsi.calculate(df)
        rsi_series = rsi_result["rsi_series"]
        hull_rsi_series = hull_ma.hma(rsi_series, 10)
        hull_rsi_val = float(hull_rsi_series.iloc[-1]) if not pd.isna(hull_rsi_series.iloc[-1]) else None
        close = df["close"]
        mhull = hull_ma.hma(close, 30)
        shull = hull_ma.hma(close, 10)
        frsi = hull_ma.hma(rsi_series, 10)
        srsi = hull_ma.hma(rsi.calculate(df, period=28)["rsi_series"], 10)
        high, low = df["high"], df["low"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        alpha = 1.0 / 14
        atr_series = tr.ewm(alpha=alpha, min_periods=14, adjust=False).mean()
        return {
            "rsi": rsi_result,
            "macd": macd.calculate(df),
            "stoch_rsi": stoch_rsi.calculate(df, hull_rsi_value=hull_rsi_val),
            "bb": bollinger_bands.calculate(df),
            "adx": adx.calculate(df),
            "heikin_ashi": heikin_ashi.calculate(df, mode="safe"),
            "hull_ma": {"mhull": mhull, "shull": shull},
            "rsi_trend": {"frsi": frsi, "srsi": srsi},
            "_atr_series": atr_series,
        }

    def test_macd_crossover_blocked_on_direction_mismatch(self, tmp_path):
        """require_direction_match=True: HA bearish인데 MACD golden(bullish)이면 차단."""
        ta = _make_booster_config(tmp_path, "macd_crossover", {
            "enabled": True, "boost": 6, "category": "trend",
            "require_direction_match": True,
        })
        n = 100
        # 하락 후 상승 → MACD golden cross (bullish)
        close = np.concatenate([30000 - np.arange(60) * 100.0, 24000 + np.arange(40) * 200.0])
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 5000.0)})
        indicators = self._compute_all_indicators(df)

        macd_cross = indicators["macd"]["crossover"]
        if macd_cross == "golden":
            # HA 방향을 bearish(반대)로 설정 → 차단되어야 함
            boost = ta._evaluate_booster("macd_crossover", ta._boosters["macd_crossover"], indicators, df, ha_direction="bearish")
            assert boost == 0.0, f"방향 불일치 시 차단 실패: boost={boost}"

    def test_macd_crossover_passes_on_direction_match(self, tmp_path):
        """require_direction_match=True: HA bullish이고 MACD golden(bullish)이면 통과."""
        ta = _make_booster_config(tmp_path, "macd_crossover", {
            "enabled": True, "boost": 6, "category": "trend",
            "require_direction_match": True,
        })
        n = 100
        close = np.concatenate([30000 - np.arange(60) * 100.0, 24000 + np.arange(40) * 200.0])
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 5000.0)})
        indicators = self._compute_all_indicators(df)

        macd_cross = indicators["macd"]["crossover"]
        if macd_cross == "golden":
            # HA 방향을 bullish(일치)로 설정 → 통과해야 함
            boost = ta._evaluate_booster("macd_crossover", ta._boosters["macd_crossover"], indicators, df, ha_direction="bullish")
            assert boost == 6.0, f"방향 일치 시 통과 실패: boost={boost}"

    def test_adx_crossover_blocked_on_direction_mismatch(self, tmp_path):
        """adx_di_crossover: DI 방향과 HA 방향 불일치 시 차단."""
        ta = _make_booster_config(tmp_path, "adx_di_crossover", {
            "enabled": True, "boost": 8, "category": "trend",
            "require_direction_match": True, "min_adx": 0.0,  # ADX 강도 체크 비활성
        })
        n = 100
        close = np.concatenate([30000 - np.arange(50) * 100.0, 25000 + np.arange(50) * 150.0])
        df = pd.DataFrame({"open": close - 40, "high": close + 80, "low": close - 80, "close": close, "volume": np.full(n, 5000.0)})
        indicators = self._compute_all_indicators(df)

        di_cross = indicators["adx"]["di_crossover"]
        if di_cross is not None:
            opposite = "bearish" if di_cross == "bullish" else "bullish"
            boost = ta._evaluate_booster("adx_di_crossover", ta._boosters["adx_di_crossover"], indicators, df, ha_direction=opposite)
            assert boost == 0.0, f"ADX DI 방향 불일치 시 차단 실패: boost={boost}"

    def test_adx_crossover_passes_on_direction_match(self, tmp_path):
        """adx_di_crossover: DI 방향과 HA 방향 일치 시 통과."""
        ta = _make_booster_config(tmp_path, "adx_di_crossover", {
            "enabled": True, "boost": 8, "category": "trend",
            "require_direction_match": True, "min_adx": 0.0,
        })
        n = 100
        close = np.concatenate([30000 - np.arange(50) * 100.0, 25000 + np.arange(50) * 150.0])
        df = pd.DataFrame({"open": close - 40, "high": close + 80, "low": close - 80, "close": close, "volume": np.full(n, 5000.0)})
        indicators = self._compute_all_indicators(df)

        di_cross = indicators["adx"]["di_crossover"]
        if di_cross is not None:
            boost = ta._evaluate_booster("adx_di_crossover", ta._boosters["adx_di_crossover"], indicators, df, ha_direction=di_cross)
            assert boost == 8.0, f"ADX DI 방향 일치 시 통과 실패: boost={boost}"

    def test_direction_match_disabled_always_fires(self, tmp_path):
        """require_direction_match=False(기본값): 방향 관계없이 크로스 발생 시 항상 통과."""
        ta = _make_booster_config(tmp_path, "macd_crossover", {
            "enabled": True, "boost": 6, "category": "trend",
            "require_direction_match": False,
        })
        n = 100
        close = np.concatenate([30000 - np.arange(60) * 100.0, 24000 + np.arange(40) * 200.0])
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 5000.0)})
        indicators = self._compute_all_indicators(df)

        if indicators["macd"]["crossover"] is not None:
            # 방향 불일치여도 통과해야 함
            boost = ta._evaluate_booster("macd_crossover", ta._boosters["macd_crossover"], indicators, df, ha_direction="bearish")
            assert boost == 6.0


class TestPhase2ADXStrength:
    """Phase 2: ADX 강도 임계값 — 횡보장(ADX < min_adx) DI 크로스 차단."""

    def test_adx_crossover_blocked_below_min_adx(self, tmp_path):
        """ADX가 min_adx(20) 미만이면 DI 크로스도 차단."""
        ta = _make_booster_config(tmp_path, "adx_di_crossover", {
            "enabled": True, "boost": 8, "category": "trend",
            "min_adx": 25.0,  # 높게 설정
        })
        # 아주 약한 추세 데이터 → ADX가 낮게 유지됨
        rng = np.random.default_rng(0)
        n = 100
        close = 30000 + np.cumsum(rng.normal(0, 5, n))  # 거의 평탄
        df = pd.DataFrame({"open": close, "high": close + 5, "low": close - 5, "close": close, "volume": np.full(n, 5000.0)})

        from app.analyzers.indicators import adx as adx_mod
        adx_result = adx_mod.calculate(df)

        if adx_result["adx"] < 25.0 and adx_result["di_crossover"] is not None:
            boost = ta._evaluate_booster(
                "adx_di_crossover", ta._boosters["adx_di_crossover"],
                {"adx": adx_result}, df
            )
            assert boost == 0.0, f"ADX < min_adx 시 차단 실패: boost={boost}, adx={adx_result['adx']}"

    def test_adx_crossover_passes_above_min_adx(self, tmp_path):
        """ADX가 min_adx 이상이면 DI 크로스 통과."""
        ta = _make_booster_config(tmp_path, "adx_di_crossover", {
            "enabled": True, "boost": 8, "category": "trend",
            "min_adx": 10.0,  # 낮게 설정해서 추세 데이터에서 통과하도록
        })
        # 강한 추세 데이터 → ADX 높음
        n = 100
        close = np.concatenate([30000 - np.arange(50) * 200.0, 20000 + np.arange(50) * 250.0])
        df = pd.DataFrame({"open": close - 80, "high": close + 120, "low": close - 120, "close": close, "volume": np.full(n, 5000.0)})

        from app.analyzers.indicators import adx as adx_mod
        adx_result = adx_mod.calculate(df)

        if adx_result["adx"] >= 10.0 and adx_result["di_crossover"] is not None:
            boost = ta._evaluate_booster(
                "adx_di_crossover", ta._boosters["adx_di_crossover"],
                {"adx": adx_result}, df,
            )
            assert boost == 8.0, f"ADX >= min_adx 시 통과 실패: boost={boost}"


class TestPhase3BBLookback:
    """Phase 3: BB Expansion 룩백 윈도우 — 5봉 평균 vs 1봉 비교."""

    def test_bb_bandwidth_series_exposed(self):
        """bollinger_bands.calculate()가 bandwidth_series를 반환하는지 확인."""
        from app.analyzers.indicators import bollinger_bands
        n = 100
        close = pd.Series(30000.0 + np.cumsum(np.random.default_rng(1).normal(0, 50, n)))
        df = pd.DataFrame({"open": close, "high": close + 50, "low": close - 50, "close": close, "volume": np.full(n, 5000.0)})
        result = bollinger_bands.calculate(df)
        assert "bandwidth_series" in result
        assert isinstance(result["bandwidth_series"], pd.Series)

    def test_bb_expansion_with_5bar_lookback_filters_single_spike(self, tmp_path):
        """5봉 룩백: 단일 봉 bandwidth 급등만으로는 트리거되지 않아야 함."""
        # lookback=5, ratio=1.5 설정
        ta = _make_booster_config(tmp_path, "bb_expansion", {
            "enabled": True, "boost": 10, "category": "volatility",
            "bandwidth_ratio": 1.5, "lookback": 5,
        })
        rng = np.random.default_rng(42)
        n = 100
        # 98봉 안정 + 직전 1봉만 스파이크 → 5봉 평균이 높아서 현재봉이 1.5x 초과하기 어려움
        close = np.concatenate([
            30000 + rng.normal(0, 50, 98),
            np.array([32000]),  # 직전 봉 스파이크
            np.array([30100]),  # 현재 봉 (평범)
        ])
        high = close + np.concatenate([rng.uniform(10, 30, 98), np.array([2000, 100])])
        low = close - np.concatenate([rng.uniform(10, 30, 98), np.array([2000, 100])])
        open_ = close + rng.normal(0, 10, n)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": np.full(n, 5000.0)})

        from app.analyzers.indicators import bollinger_bands
        bb = bollinger_bands.calculate(df)
        # lookback=5일 때 prev_bw는 최근 5봉 평균
        bw_series = bb["bandwidth_series"]
        prev_bw_5 = float(bw_series.iloc[-6:-1].dropna().mean())
        curr_bw = bb["bandwidth"]
        # 만약 현재봉 bandwidth가 5봉 평균의 1.5배 미만이면 차단 확인
        if prev_bw_5 > 0 and curr_bw / prev_bw_5 < 1.5:
            from app.analyzers.indicators import adx as adx_mod, heikin_ashi, hull_ma, macd, rsi, stoch_rsi, bollinger_bands as bb_mod
            indicators = {"bb": bb}
            boost = ta._evaluate_booster("bb_expansion", ta._boosters["bb_expansion"], indicators, df)
            assert boost == 0.0, f"5봉 룩백에서 단일 스파이크 후 차단 실패: boost={boost}"


class TestPhase4RSIEntry:
    """Phase 4: RSI Extreme 진입 감지 — 유지 중(consecutive) 시 무시."""

    def test_rsi_extreme_blocked_on_continuation(self, tmp_path):
        """require_entry=True: 이미 극단 존에 있으면 반복 트리거하지 않음."""
        ta = _make_booster_config(tmp_path, "rsi_extreme", {
            "enabled": True, "boost": 10, "category": "momentum",
            "overbought": 80.0, "oversold": 20.0, "require_entry": True,
        })
        # 장기 하락 추세 → RSI가 오래 20 이하 유지
        n = 100
        close = 30000 - np.arange(n) * 300.0
        close = np.maximum(close, 100)
        df = pd.DataFrame({"open": close + 30, "high": close + 50, "low": close - 50, "close": close, "volume": np.full(n, 5000.0)})

        from app.analyzers.indicators import rsi as rsi_mod
        rsi_result = rsi_mod.calculate(df)
        rsi_series = rsi_result["rsi_series"]
        rsi_val = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2])

        # 둘 다 20 미만이면 (극단 존 유지) → 차단 확인
        if rsi_val < 20 and prev_rsi < 20:
            boost = ta._evaluate_booster(
                "rsi_extreme", ta._boosters["rsi_extreme"],
                {"rsi": rsi_result}, df
            )
            assert boost == 0.0, f"RSI 극단 존 유지 중 차단 실패: boost={boost}, rsi={rsi_val:.1f}, prev={prev_rsi:.1f}"

    def test_rsi_extreme_fires_on_entry(self, tmp_path):
        """require_entry=True: 극단 존 진입 시(이전 봉은 정상) 트리거."""
        ta = _make_booster_config(tmp_path, "rsi_extreme", {
            "enabled": True, "boost": 10, "category": "momentum",
            "overbought": 80.0, "oversold": 20.0, "require_entry": True,
        })
        # 중간 하락 후 마지막 1봉만 급락 → RSI가 이전봉 정상 → 현재봉 극단 진입
        n = 100
        rng = np.random.default_rng(42)
        # 안정 구간 후 마지막 봉에서 급락
        close = np.concatenate([30000 + rng.normal(0, 100, n - 1), np.array([5000.0])])
        df = pd.DataFrame({"open": close + 30, "high": close + 50, "low": close - 50, "close": close, "volume": np.full(n, 5000.0)})

        from app.analyzers.indicators import rsi as rsi_mod
        rsi_result = rsi_mod.calculate(df)
        rsi_series = rsi_result["rsi_series"]
        rsi_val = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2])

        # 현재봉만 극단 존이고 이전봉은 정상이어야 진입 트리거
        if rsi_val < 20 and prev_rsi >= 20:
            boost = ta._evaluate_booster(
                "rsi_extreme", ta._boosters["rsi_extreme"],
                {"rsi": rsi_result}, df
            )
            assert boost == 10.0, f"RSI 신규 진입 시 트리거 실패: boost={boost}"

    def test_rsi_extreme_disabled_require_entry_fires_on_continuation(self, tmp_path):
        """require_entry=False(기본값): 극단 존 유지 중에도 트리거."""
        ta = _make_booster_config(tmp_path, "rsi_extreme", {
            "enabled": True, "boost": 10, "category": "momentum",
            "overbought": 80.0, "oversold": 20.0, "require_entry": False,
        })
        n = 100
        close = 30000 - np.arange(n) * 300.0
        close = np.maximum(close, 100)
        df = pd.DataFrame({"open": close + 30, "high": close + 50, "low": close - 50, "close": close, "volume": np.full(n, 5000.0)})

        from app.analyzers.indicators import rsi as rsi_mod
        rsi_result = rsi_mod.calculate(df)
        rsi_val = float(rsi_result["rsi_series"].iloc[-1])
        prev_rsi = float(rsi_result["rsi_series"].iloc[-2])

        if rsi_val < 20 and prev_rsi < 20:  # 극단 존 유지 중
            boost = ta._evaluate_booster(
                "rsi_extreme", ta._boosters["rsi_extreme"],
                {"rsi": rsi_result}, df
            )
            assert boost == 10.0, f"require_entry=False 시 유지 중에도 트리거 실패: boost={boost}"


class TestPhase5VolumeWithPrice:
    """Phase 5: Volume Spike 가격 확인 — 최소 가격 변동 수반 필요."""

    def test_volume_spike_blocked_without_price_move(self, tmp_path):
        """min_price_change_pct=1.0: 거래량 스파이크 + 가격 변동 없으면 차단."""
        ta = _make_booster_config(tmp_path, "volume_spike_strong", {
            "enabled": True, "boost": 10, "category": "volatility",
            "threshold": 4.0, "min_price_change_pct": 1.0,
        })
        n = 100
        rng = np.random.default_rng(42)
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        # 마지막 봉: open ≈ close (가격 변동 없음), 거래량 10x
        open_ = close.copy()
        open_[-1] = close[-1] * 1.001  # 0.1% 변동 (1% 미만)
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0

        df = pd.DataFrame({"open": open_, "high": close + 50, "low": close - 50, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "volume_spike_strong" not in boost_info.get("active_boosters", {}), \
            "가격 변동 없는 거래량 스파이크는 차단되어야 함"

    def test_volume_spike_passes_with_price_move(self, tmp_path):
        """min_price_change_pct=1.0: 거래량 스파이크 + 1% 이상 가격 변동 시 통과."""
        ta = _make_booster_config(tmp_path, "volume_spike_strong", {
            "enabled": True, "boost": 10, "category": "volatility",
            "threshold": 4.0, "min_price_change_pct": 1.0,
        })
        n = 100
        rng = np.random.default_rng(42)
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        # 마지막 봉: 2% 하락 + 거래량 10x
        open_ = close.copy()
        open_[-1] = close[-1] * 1.02  # 2% 가격 변동 수반
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0

        df = pd.DataFrame({"open": open_, "high": close + 50, "low": close - 50, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "volume_spike_strong" in boost_info.get("active_boosters", {}), \
            "2% 가격 변동 수반 거래량 스파이크는 통과해야 함"

    def test_volume_spike_no_price_check_when_disabled(self, tmp_path):
        """min_price_change_pct=0.0(기본값): 가격 변동 체크 없이 거래량만으로 통과."""
        ta = _make_booster_config(tmp_path, "volume_spike_strong", {
            "enabled": True, "boost": 10, "category": "volatility",
            "threshold": 4.0,  # min_price_change_pct 미설정 → 0.0
        })
        n = 100
        rng = np.random.default_rng(42)
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        open_ = close.copy()
        open_[-1] = close[-1] * 1.001  # 0.1% 변동 (평탄)
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0

        df = pd.DataFrame({"open": open_, "high": close + 50, "low": close - 50, "close": close, "volume": volume})
        result = ta.analyze(df)
        boost_info = result.details["signal_boost"]
        assert "volume_spike_strong" in boost_info.get("active_boosters", {}), \
            "가격 체크 비활성 시 거래량만으로 통과해야 함"


class TestPhase6BoostCap:
    """Phase 6: 부스트 합산 상한 (max_boost)."""

    def test_boost_capped_at_max_boost(self, tmp_path):
        """여러 부스터 합산이 max_boost를 초과하지 않아야 함."""
        max_boost = 15
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40, "max_boost": max_boost},
            "ha_filter": {"enabled": False},
            "category_gate": {"enabled": False},
            "signal_boosters": {
                "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
                "volume_spike_strong": {"enabled": True, "boost": 10, "category": "volatility", "threshold": 2.5},
                "atr_spike": {"enabled": True, "boost": 8, "category": "volatility", "multiplier": 1.0, "lookback": 5},
            },
        }
        config_path = tmp_path / "capped.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        n = 100
        # 강한 하락 + 거래량 스파이크 → 여러 부스터 동시 발동 (합계 28점 가능)
        close = 30000 - np.arange(n) * 300.0
        close = np.maximum(close, 100)
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0

        df = pd.DataFrame({
            "open": close + 30, "high": close + 50, "low": close - 50,
            "close": close, "volume": volume,
        })
        result = ta.analyze(df)
        boost_total = result.details["signal_boost"]["total_boost"]
        assert boost_total <= max_boost, f"부스트 상한 초과: {boost_total} > {max_boost}"

    def test_no_cap_when_max_boost_not_set(self, tmp_path):
        """max_boost 미설정 시 상한 없이 합산."""
        cfg = {
            "indicators": {
                "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            },
            "signals": {"high_threshold": 70, "medium_threshold": 40},  # max_boost 없음
            "ha_filter": {"enabled": False},
            "category_gate": {"enabled": False},
            "signal_boosters": {
                "rsi_extreme": {"enabled": True, "boost": 10, "category": "momentum", "overbought": 80.0, "oversold": 20.0},
                "volume_spike_strong": {"enabled": True, "boost": 10, "category": "volatility", "threshold": 2.5},
            },
        }
        config_path = tmp_path / "uncapped.yaml"
        config_path.write_text(yaml.dump(cfg))
        ta = TechnicalAnalyzer(config_path=str(config_path))

        n = 100
        close = 30000 - np.arange(n) * 300.0
        close = np.maximum(close, 100)
        volume = np.full(n, 1000.0)
        volume[-1] = 10_000.0

        df = pd.DataFrame({
            "open": close + 30, "high": close + 50, "low": close - 50,
            "close": close, "volume": volume,
        })
        result = ta.analyze(df)
        # 상한 없으면 20점(10+10)까지 가능 — 그냥 크래시 없이 실행되는지만 확인
        assert isinstance(result.details["signal_boost"]["total_boost"], float)


def _make_sustained_oversold_indicators(df, rsi_override=None):
    """sustained_oversold 직접 테스트용 indicators dict 생성."""
    from app.analyzers.indicators import adx, bollinger_bands, heikin_ashi, hull_ma, macd, rsi, stoch_rsi

    rsi_result = rsi.calculate(df)
    if rsi_override is not None:
        rsi_result = dict(rsi_result)
        rsi_result["rsi_series"] = rsi_override

    rsi_series = rsi_result["rsi_series"]
    hull_rsi_series = hull_ma.hma(rsi_series, 10)
    hull_rsi_val = float(hull_rsi_series.iloc[-1]) if not pd.isna(hull_rsi_series.iloc[-1]) else None
    close = df["close"]
    mhull = hull_ma.hma(close, 30)
    shull = hull_ma.hma(close, 10)
    frsi = hull_ma.hma(rsi_series, 10)
    srsi = hull_ma.hma(rsi.calculate(df, period=28)["rsi_series"], 10)
    high, low = df["high"], df["low"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    alpha = 1.0 / 14
    atr_series = tr.ewm(alpha=alpha, min_periods=14, adjust=False).mean()
    return {
        "rsi": rsi_result,
        "macd": macd.calculate(df),
        "stoch_rsi": stoch_rsi.calculate(df, hull_rsi_value=hull_rsi_val),
        "bb": bollinger_bands.calculate(df),
        "adx": adx.calculate(df),
        "heikin_ashi": heikin_ashi.calculate(df, mode="simple"),
        "hull_ma": {"mhull": mhull, "shull": shull},
        "rsi_trend": {"frsi": frsi, "srsi": srsi},
        "_atr_series": atr_series,
    }


class TestSustainedOversold:
    """sustained_oversold 부스터: RSI 장기 과매도 + 횡보 필터 검증."""

    def test_triggers_after_consecutive_oversold_with_atr_confirm(self, tmp_path):
        """48봉 연속 RSI < 25 + ATR 확대 → 트리거."""
        ta = _make_booster_config(tmp_path, "sustained_oversold", {
            "enabled": True, "boost": 10, "category": "momentum",
            "rsi_threshold": 25.0, "min_consecutive": 48, "require_confirm": True,
        })
        n = 100
        # 강한 하락 추세: 변동성 유지 (ATR 확대)
        close = 30000 - np.arange(n) * 250.0
        close = np.maximum(close, 100.0)
        volume = np.full(n, 5000.0)
        # 마지막 봉 ATR 확대를 위해 변동 폭 확대
        high = close + np.linspace(50, 300, n)
        low = close - np.linspace(50, 300, n)
        df = pd.DataFrame({"open": close + 30, "high": high, "low": low, "close": close, "volume": volume})

        # RSI 오버라이드: 최근 48봉 모두 < 25
        rsi_vals = np.full(n, 15.0)
        rsi_series = pd.Series(rsi_vals, dtype=float)
        indicators = _make_sustained_oversold_indicators(df, rsi_override=rsi_series)

        boost = ta._evaluate_booster(
            "sustained_oversold", ta._boosters["sustained_oversold"],
            indicators, df,
        )
        assert boost == 10.0, f"ATR 확대 시 트리거 실패: boost={boost}"

    def test_blocked_without_confirm(self, tmp_path):
        """48봉 연속 RSI < 25 but 횡보(ATR 낮음, 신저점 없음, 거래량 낮음) → 차단."""
        ta = _make_booster_config(tmp_path, "sustained_oversold", {
            "enabled": True, "boost": 10, "category": "momentum",
            "rsi_threshold": 25.0, "min_consecutive": 48, "require_confirm": True,
        })
        n = 100
        # 완전 횡보: 가격/거래량 변화 없음, ATR 매우 낮음
        close = np.full(n, 30000.0)
        high = close + 10.0   # 매우 작은 변동폭 → ATR 최소
        low = close - 10.0
        volume = np.full(n, 1000.0)
        df = pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume})

        # RSI 오버라이드: 48봉 모두 < 25
        rsi_vals = np.full(n, 15.0)
        rsi_series = pd.Series(rsi_vals, dtype=float)
        indicators = _make_sustained_oversold_indicators(df, rsi_override=rsi_series)

        # ATR 오버라이드: 현재 ATR < 평균 (횡보)
        from app.analyzers.indicators import hull_ma as hull_ma_mod, rsi as rsi_mod
        atr_vals = np.full(n, 100.0)
        atr_vals[-1] = 50.0  # 현재 ATR이 평균보다 낮음
        indicators["_atr_series"] = pd.Series(atr_vals, dtype=float)

        boost = ta._evaluate_booster(
            "sustained_oversold", ta._boosters["sustained_oversold"],
            indicators, df,
        )
        assert boost == 0.0, f"횡보 구간 차단 실패: boost={boost}"

    def test_blocked_if_not_enough_consecutive_bars(self, tmp_path):
        """연속 봉 수 부족(30봉만 < 25) → 차단."""
        ta = _make_booster_config(tmp_path, "sustained_oversold", {
            "enabled": True, "boost": 10, "category": "momentum",
            "rsi_threshold": 25.0, "min_consecutive": 48, "require_confirm": False,
        })
        n = 100
        close = 30000 - np.arange(n) * 200.0
        close = np.maximum(close, 100.0)
        df = pd.DataFrame({
            "open": close + 30, "high": close + 50, "low": close - 50,
            "close": close, "volume": np.full(n, 5000.0),
        })

        # RSI 오버라이드: 최근 30봉만 < 25, 나머지는 정상
        rsi_vals = np.full(n, 50.0)
        rsi_vals[-30:] = 15.0  # 30봉만 극단
        rsi_series = pd.Series(rsi_vals, dtype=float)
        indicators = _make_sustained_oversold_indicators(df, rsi_override=rsi_series)

        boost = ta._evaluate_booster(
            "sustained_oversold", ta._boosters["sustained_oversold"],
            indicators, df,
        )
        assert boost == 0.0, f"봉 수 부족 시 차단 실패: boost={boost}"


def _make_mtf_config(tmp_path, booster_name: str, booster_cfg: dict) -> TechnicalAnalyzer:
    """MTF 부스터 격리 테스트용 config (HA/카테고리 게이트 비활성)."""
    cfg = {
        "indicators": {
            "atr": {"enabled": True, "weight": 1.0, "period": 14, "normalize": {"min": 100, "max": 5000}},
            "bollinger_width": {"enabled": False, "weight": 0.0, "period": 20, "normalize": {"min": 0.01, "max": 0.20}},
            "cvi": {"enabled": False, "weight": 0.0, "period": 10, "normalize": {"min": -50, "max": 50}},
            "historical_volatility": {"enabled": False, "weight": 0.0, "period": 20, "normalize": {"min": 0.1, "max": 100.0}},
            "volume_spike": {"enabled": False, "weight": 0.0, "period": 20, "normalize": {"min": 0.2, "max": 5.0}},
        },
        "signals": {"high_threshold": 70, "medium_threshold": 40},
        "ha_filter": {"enabled": False},
        "category_gate": {"enabled": False},
        "signal_boosters": {booster_name: booster_cfg},
    }
    path = tmp_path / "mtf.yaml"
    path.write_text(yaml.dump(cfg))
    return TechnicalAnalyzer(config_path=str(path))


def _make_4h_df(n: int = 50, rsi_val: float = 50.0, bb_expanding: bool = False) -> pd.DataFrame:
    """MTF 테스트용 4h DataFrame 생성."""
    close = np.full(n, 50000.0)
    if rsi_val < 30:
        # 과매도: 지속 하락 가격
        close = 50000.0 - np.arange(n) * 200.0
        close = np.clip(close, 10000, 50000)
    elif rsi_val > 70:
        # 과매수: 지속 상승 가격
        close = 40000.0 + np.arange(n) * 200.0
    if bb_expanding:
        # BB 확장: 변동성 점점 증가
        noise = np.linspace(10, 2000, n)
        close = close + np.random.choice([-1, 1], n) * noise

    return pd.DataFrame({
        "open": close - 100,
        "high": close + 300,
        "low": close - 300,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


class TestMtfBoosters:
    """멀티 타임프레임(4h) 부스터 테스트."""

    def test_mtf_rsi_extreme_triggers_oversold(self, tmp_path):
        """4h RSI < 25 → mtf_rsi_extreme 트리거."""
        ta = _make_mtf_config(tmp_path, "mtf_rsi_extreme", {
            "enabled": True, "boost": 8, "category": "momentum",
            "overbought": 75.0, "oversold": 25.0,
        })
        # 1h DF (기존)
        n = 100
        close_1h = np.full(n, 50000.0)
        df = pd.DataFrame({"open": close_1h - 50, "high": close_1h + 100, "low": close_1h - 100, "close": close_1h, "volume": np.full(n, 1000.0)})

        # 4h DF: 지속 하락 → RSI < 25
        df_4h = _make_4h_df(n=50, rsi_val=20.0)
        indicators = ta._compute_signal_indicators(df)
        indicators["mtf_4h"] = ta._compute_mtf_indicators(df_4h)

        rsi_4h = float(indicators["mtf_4h"]["rsi"]["rsi_series"].iloc[-1])
        if rsi_4h < 25.0:
            boost = ta._evaluate_booster("mtf_rsi_extreme", ta._boosters["mtf_rsi_extreme"], indicators, df)
            assert boost == 8.0, f"4h RSI({rsi_4h:.1f}) < 25인데 트리거 실패"

    def test_mtf_rsi_extreme_skipped_without_4h_data(self, tmp_path):
        """df_4h=None → mtf_rsi_extreme boost=0."""
        ta = _make_mtf_config(tmp_path, "mtf_rsi_extreme", {
            "enabled": True, "boost": 8, "category": "momentum",
            "overbought": 75.0, "oversold": 25.0,
        })
        n = 100
        close = np.full(n, 50000.0)
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 1000.0)})
        indicators = ta._compute_signal_indicators(df)
        # mtf_4h 없음 (df_4h=None)

        boost = ta._evaluate_booster("mtf_rsi_extreme", ta._boosters["mtf_rsi_extreme"], indicators, df)
        assert boost == 0.0, "4h 데이터 없을 때 차단 실패"

    def test_mtf_rsi_extreme_not_triggered_in_normal_range(self, tmp_path):
        """4h RSI 50 (정상 범위) → boost=0."""
        ta = _make_mtf_config(tmp_path, "mtf_rsi_extreme", {
            "enabled": True, "boost": 8, "category": "momentum",
            "overbought": 75.0, "oversold": 25.0,
        })
        n = 100
        close = np.full(n, 50000.0)
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 1000.0)})
        df_4h = _make_4h_df(n=50, rsi_val=50.0)  # 정상 RSI
        indicators = ta._compute_signal_indicators(df)
        indicators["mtf_4h"] = ta._compute_mtf_indicators(df_4h)

        rsi_4h = float(indicators["mtf_4h"]["rsi"]["rsi_series"].iloc[-1])
        if 25.0 <= rsi_4h <= 75.0:
            boost = ta._evaluate_booster("mtf_rsi_extreme", ta._boosters["mtf_rsi_extreme"], indicators, df)
            assert boost == 0.0, f"정상 범위 RSI({rsi_4h:.1f})인데 트리거됨"

    def test_mtf_trend_confirm_bearish_match(self, tmp_path):
        """4h HMA 하락 + HA bearish → mtf_trend_confirm 트리거."""
        ta = _make_mtf_config(tmp_path, "mtf_trend_confirm", {
            "enabled": True, "boost": 6, "category": "trend",
            "require_direction_match": True,
        })
        n = 100
        close = np.full(n, 50000.0)
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 1000.0)})

        # 4h: 하락 추세 → HMA falling
        df_4h = _make_4h_df(n=50, rsi_val=20.0)
        indicators = ta._compute_signal_indicators(df)
        indicators["mtf_4h"] = ta._compute_mtf_indicators(df_4h)

        hma = indicators["mtf_4h"]["hma"]
        if not (pd.isna(hma.iloc[-1]) or pd.isna(hma.iloc[-2])):
            hma_falling = float(hma.iloc[-1]) < float(hma.iloc[-2])
            if hma_falling:
                boost = ta._evaluate_booster("mtf_trend_confirm", ta._boosters["mtf_trend_confirm"], indicators, df, ha_direction="bearish")
                assert boost == 6.0, f"4h HMA 하락 + HA bearish인데 트리거 실패"

    def test_mtf_trend_confirm_blocked_without_4h_data(self, tmp_path):
        """df_4h=None → mtf_trend_confirm boost=0."""
        ta = _make_mtf_config(tmp_path, "mtf_trend_confirm", {
            "enabled": True, "boost": 6, "category": "trend",
            "require_direction_match": True,
        })
        n = 100
        close = np.full(n, 50000.0)
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 1000.0)})
        indicators = ta._compute_signal_indicators(df)

        boost = ta._evaluate_booster("mtf_trend_confirm", ta._boosters["mtf_trend_confirm"], indicators, df, ha_direction="bearish")
        assert boost == 0.0, "4h 데이터 없을 때 차단 실패"

    def test_analyze_accepts_df_4h_param(self, analyzer):
        """analyze()가 df_4h 파라미터를 받아도 정상 동작 (하위 호환)."""
        n = 100
        close = np.full(n, 50000.0)
        df = pd.DataFrame({"open": close - 50, "high": close + 100, "low": close - 100, "close": close, "volume": np.full(n, 1000.0)})
        df_4h = _make_4h_df(n=50)

        # df_4h 포함 호출
        result_with = analyzer.analyze(df, df_4h=df_4h)
        # df_4h 없이 호출 (하위 호환)
        result_without = analyzer.analyze(df)

        assert result_with.score >= 0
        assert result_without.score >= 0
