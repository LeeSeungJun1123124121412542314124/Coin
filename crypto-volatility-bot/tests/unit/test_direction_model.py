"""방향 모델 단위 테스트 — compute_direction()."""

from __future__ import annotations

from app.analyzers.direction_model import compute_direction


# ── 1차 방향 게이트 (4건) ────────────────────────────────────
def test_ha_bullish_both_golden_long():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross="golden", macd_cross="golden",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "long"
    assert b.final_direction == "long"


def test_ha_bullish_both_death_downgrade_neutral():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross="death", macd_cross="death",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "neutral"
    assert b.final_direction == "neutral"


def test_ha_bearish_one_oppose_stays_short():
    b = compute_direction(
        ha_bullish=False, ha_bearish=True, hma_cross="death", macd_cross="golden",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "short"


def test_ha_bullish_one_death_stays_long():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross="golden", macd_cross="death",
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.primary_direction == "long"


# ── 신뢰도 가감 (4건) ────────────────────────────────────────
def test_all_confirm_high_confidence():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=-0.001, flow_ratio=0.8, mvrv=0.5, fear_greed=10,
    )
    assert b.confidence == 100.0
    assert b.final_direction == "long"
    assert b.confirm_count == 2
    assert b.divergence_count == 0


def test_all_divergence_low_confidence():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=0.001, flow_ratio=1.5, mvrv=4.0, fear_greed=90,
    )
    assert b.confidence == 0.0
    assert b.final_direction == "neutral"
    assert b.divergence_count == 2


def test_mvrv_extreme_nudge_only():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=None, mvrv=4.0, fear_greed=None,
    )
    assert b.confidence == 40.0
    assert b.final_direction == "long"


def test_fg_extreme_nudge_only():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=10,
    )
    assert b.confidence == 60.0
    assert b.final_direction == "long"


# ── deadband (3건) ───────────────────────────────────────────
def test_fr_deadband_zero():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=0.00001, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.confidence == 50.0
    assert b.confirm_count == 0 and b.divergence_count == 0


def test_flow_deadband_zero():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=1.0, mvrv=None, fear_greed=None,
    )
    assert b.confidence == 50.0
    assert b.confirm_count == 0 and b.divergence_count == 0


def test_missing_inputs_zero():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
    )
    assert b.confidence == 50.0
    assert b.final_direction == "long"


# ── 컷오프 (1건) ─────────────────────────────────────────────
def test_confidence_below_cutoff_neutral():
    b = compute_direction(
        ha_bullish=True, ha_bearish=False, hma_cross=None, macd_cross=None,
        funding_rate=0.001, flow_ratio=None, mvrv=4.0, fear_greed=None,
    )
    assert b.confidence == 25.0
    assert b.primary_direction == "long"
    assert b.final_direction == "neutral"


def test_technical_analyzer_surfaces_direction_inputs(sample_ohlcv_df):
    from app.analyzers.technical_analyzer import TechnicalAnalyzer

    result = TechnicalAnalyzer().analyze(sample_ohlcv_df)
    d = result.details
    assert d["ha_direction"] in ("bullish", "bearish", "neutral")
    assert d["hma_cross"] in ("golden", "death", None)
    assert d["macd_cross"] in ("golden", "death", None)


def test_aggregator_attaches_direction():
    from app.analyzers.base import AnalysisResult
    from app.analyzers.score_aggregator import ScoreAggregator

    onchain = AnalysisResult(score=50, signal="NEUTRAL",
                             details={"flow_ratio": 0.8, "mvrv": 0.5, "whale_alert": False})
    technical = AnalysisResult(score=50, signal="LOW",
                               details={"ha_direction": "bullish", "hma_cross": "golden",
                                        "macd_cross": "golden"})
    sentiment = AnalysisResult(score=50, signal="NEUTRAL", details={"fear_greed_index": 10})

    agg = ScoreAggregator().aggregate(onchain, technical, sentiment, derivatives=None)
    assert agg.direction is not None
    assert agg.direction.final_direction == "long"
