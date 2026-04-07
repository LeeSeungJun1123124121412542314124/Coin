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
        },
    )


@pytest.fixture
def formatter() -> MessageFormatter:
    return MessageFormatter()


class TestPeriodicReport:
    def test_contains_score(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert "65" in msg or "65.0" in msg

    def test_contains_symbol(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert "BTC" in msg

    def test_contains_alert_level(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert "HIGH" in msg

    def test_within_telegram_limit(self, formatter):
        msg = formatter.periodic_report("BTC/USDT", _agg())
        assert len(msg) <= 4096


class TestEmergencyAlert:
    def test_contains_emergency_header(self, formatter):
        msg = formatter.emergency_alert("BTC/USDT", _agg(score=85, alert_level="EMERGENCY"))
        assert "EMERGENCY" in msg.upper() or "긴급" in msg

    def test_within_telegram_limit(self, formatter):
        msg = formatter.emergency_alert("BTC/USDT", _agg(score=85, alert_level="EMERGENCY"))
        assert len(msg) <= 4096


class TestWhaleAlert:
    def test_contains_whale_info(self, formatter):
        msg = formatter.whale_alert("BTC/USDT", _agg(whale_alert=True))
        assert "whale" in msg.lower() or "고래" in msg

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
