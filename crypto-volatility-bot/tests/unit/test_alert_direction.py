"""알림 히스토리 방향(급등/급락) 기록 기능 테스트 — docs/SPEC_alert-direction-history.md."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.analyzers.base import AnalysisResult
from app.analyzers.score_aggregator import AggregatedResult, ScoreAggregator
from app.analyzers.technical_analyzer import TechnicalAnalyzer
from app.macro.direction_composite import DirectionTilt
from app.notifiers.message_formatter import MessageFormatter, _format_alert_direction


def _df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1.0] * len(closes)})


# ── A) 종목 기술방향 (모멘텀 부호) ───────────────────────────
def test_asset_direction_up_down_neutral():
    assert TechnicalAnalyzer._asset_direction(_df(list(range(100, 130)))) == "long"
    assert TechnicalAnalyzer._asset_direction(_df(list(range(130, 100, -1)))) == "short"
    assert TechnicalAnalyzer._asset_direction(_df([100.0] * 30)) == "neutral"


def test_asset_direction_short_series_neutral():
    assert TechnicalAnalyzer._asset_direction(_df([100.0, 101.0])) == "neutral"


# ── B) aggregator가 technical.details의 asset_direction을 surface ─
def _ar(score, details=None):
    return AnalysisResult(score=score, signal="N", details=details or {})


def test_aggregator_surfaces_asset_direction():
    res = ScoreAggregator().aggregate(
        onchain=_ar(50), technical=_ar(60, {"asset_direction": "short"}), sentiment=_ar(50)
    )
    assert res.asset_direction == "short"


def test_aggregator_asset_direction_none_when_absent():
    res = ScoreAggregator().aggregate(onchain=_ar(50), technical=_ar(60), sentiment=_ar(50))
    assert res.asset_direction is None


# ── C) formatter 방향 한 줄 ──────────────────────────────────
def _agg(asset_direction=None):
    return AggregatedResult(
        final_score=88, alert_score=88, alert_level="HIGH", whale_alert=False,
        timestamp=datetime(2026, 6, 13, tzinfo=timezone.utc),
        details={"technical_score": 88, "technical_signal": "HIGH", "derivatives_signal": "NEUTRAL"},
        asset_direction=asset_direction,
    )


def test_format_alert_direction_both():
    lines = _format_alert_direction(_agg("long"), DirectionTilt("short", 70.0, -0.7, {}, 0))
    assert lines and "급등" in lines[0] and "시장" in lines[0]


def test_format_alert_direction_empty_when_none():
    assert _format_alert_direction(_agg(None), None) == []


def test_high_alert_includes_direction_line():
    msg = MessageFormatter().high_alert("BTC/USDT", _agg("long"), market_tilt=DirectionTilt("long", 65.0, 0.65, {}, 0))
    assert "🧭 방향" in msg and "급등" in msg


# ── D) _save_alert_history가 방향 4컬럼 저장 ─────────────────
# conftest의 autouse 픽스처 _isolate_alert_cooldown_db가 _get_db를 인메모리 DB로 패치하고
# 그 커넥션을 yield하므로, 이를 받아 저장 결과를 직접 조회한다.
def test_save_alert_history_stores_direction(_isolate_alert_cooldown_db):
    from app.notification_dispatcher import _save_alert_history
    _save_alert_history("BTC/USDT", "HIGH", _agg("long"), DirectionTilt("short", 72.0, -0.72, {}, 0))
    row = _isolate_alert_cooldown_db.execute(
        "SELECT asset_direction, market_direction, market_tilt_confidence, market_tilt_z "
        "FROM alert_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["asset_direction"] == "long"
    assert row["market_direction"] == "short"
    assert row["market_tilt_confidence"] == pytest.approx(72.0)
    assert row["market_tilt_z"] == pytest.approx(-0.72)


def test_save_alert_history_null_when_no_tilt(_isolate_alert_cooldown_db):
    from app.notification_dispatcher import _save_alert_history
    _save_alert_history("ETH/USDT", "WHALE", _agg(None), None)
    row = _isolate_alert_cooldown_db.execute(
        "SELECT asset_direction, market_direction FROM alert_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["asset_direction"] is None
    assert row["market_direction"] is None
