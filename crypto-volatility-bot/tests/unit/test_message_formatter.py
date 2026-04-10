"""Tests for MessageFormatter — 6+ tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.analyzers.score_aggregator import AggregatedResult
from app.notifiers.message_formatter import MessageFormatter

_TS = datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc)


def _agg(score: float = 65.0, alert_level: str = "HIGH", whale_alert: bool = False) -> AggregatedResult:
    return AggregatedResult(
        final_score=score,
        alert_score=60.0,
        alert_level=alert_level,
        whale_alert=whale_alert,
        timestamp=_TS,
        details={
            "onchain_score": 70.0,
            "technical_score": 60.0,
            "sentiment_score": 55.0,
            "onchain_signal": "HIGH_SELL_PRESSURE",
            "technical_signal": "MEDIUM",
            "sentiment_signal": "NEUTRAL",
            "flow_ratio": 1.62,
            "fear_greed_index": 22,
            "base_score": 48.5,
            "signal_boost": {
                "total_boost": 11.5,
                "active_boosters": {"rsi_extreme": 8.0, "bb_expansion": 3.5},
            },
            "derivatives_signal": "OI_SURGE",
            "oi_3d_chg_pct": 12.3,
            "funding_rate": 0.000082,
            "whale_volume": 88.0,
        },
    )


@pytest.fixture
def formatter() -> MessageFormatter:
    return MessageFormatter()


class TestPeriodicReport:
    def test_contains_summary_section(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert "<b>한줄 요약</b>" in msg
        assert "종합 65.0/100" in msg

    def test_contains_symbol_and_level(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert "BTC" in msg
        assert "HIGH" in msg

    def test_contains_trigger_evidence(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert "<b>트리거 근거</b>" in msg
        assert "기본 48.5 + 부스터 11.5" in msg
        assert "활성 부스터: rsi_extreme(+8.0), bb_expansion(+3.5)" in msg

    def test_has_fallback_when_breakdown_missing(self, formatter):
        agg = _agg()
        agg.details.pop("base_score", None)
        agg.details.pop("signal_boost", None)
        msg = formatter.periodic_report("BTC/USDT", agg)
        assert "기술 점수 분해 데이터 없음" in msg

    def test_within_telegram_limit(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert len(msg) <= 4096


class TestConfirmedHighAlert:
    def test_contains_sections(self, formatter):
        msg = formatter.confirmed_high_alert("BTC/USDT", _agg(score=85, alert_level="CONFIRMED_HIGH"))
        assert "<b>발생 근거</b>" in msg
        assert "신뢰도 약 92%" in msg

    def test_within_telegram_limit(self, formatter):
        msg = formatter.confirmed_high_alert("BTC/USDT", _agg(score=85, alert_level="CONFIRMED_HIGH"))
        assert len(msg) <= 4096


class TestWhaleAlert:
    def test_contains_whale_info(self, formatter):
        msg = formatter.whale_alert("BTC/USDT", _agg(whale_alert=True))
        assert "whale" in msg.lower() or "고래" in msg
        assert "유입/유출 비율" in msg
        assert "고래 거래량" in msg

    def test_within_telegram_limit(self, formatter):
        msg = formatter.whale_alert("BTC/USDT", _agg(whale_alert=True))
        assert len(msg) <= 4096


class TestDailySummary:
    def test_contains_summary_label(self, formatter):
        stats = {"high": 85.0, "low": 30.0, "avg": 55.0, "date": "2026-02-17"}
        msg = formatter.daily_summary("BTC/USDT", stats)
        assert "85" in msg or "30" in msg

    def test_within_telegram_limit(self, formatter):
        stats = {"high": 85.0, "low": 30.0, "avg": 55.0, "date": "2026-02-17"}
        msg = formatter.daily_summary("BTC/USDT", stats)
        assert len(msg) <= 4096


class TestAlertLevelRecommendation:
    def test_emergency_recommendation(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg(score=85, alert_level="EMERGENCY"))
        assert len(msg) > 50

    def test_low_recommendation(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg(score=20, alert_level="LOW"))
        assert len(msg) > 50
