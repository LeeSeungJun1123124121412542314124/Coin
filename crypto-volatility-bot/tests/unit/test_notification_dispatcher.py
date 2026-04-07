"""Tests for NotificationDispatcher — event alerts and periodic reports."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.analyzers.score_aggregator import AggregatedResult
from app.notification_dispatcher import NotificationDispatcher


def _make_config(threshold: int = 80):
    """Create a minimal config-like object for testing."""

    class _FakeConfig:
        telegram_bot_token = "fake-token"
        telegram_chat_id = "fake-chat-id"

    cfg = _FakeConfig()
    cfg.emergency_threshold = threshold
    return cfg


def _make_result(
    score: float = 50.0,
    alert_score: float | None = None,
    alert_level: str = "MEDIUM",
    whale_alert: bool = False,
) -> AggregatedResult:
    return AggregatedResult(
        final_score=score,
        alert_score=alert_score if alert_score is not None else score,
        alert_level=alert_level,
        whale_alert=whale_alert,
        timestamp=datetime.now(timezone.utc),
        details={
            "onchain_score": score * 0.4,
            "technical_score": score * 0.35,
            "sentiment_score": score * 0.25,
            "onchain_signal": "NEUTRAL",
            "technical_signal": "NEUTRAL",
            "sentiment_signal": "NEUTRAL",
        },
    )


@pytest.fixture
def dispatcher():
    config = _make_config()
    d = NotificationDispatcher(config)
    d._notifier = AsyncMock()
    return d


class TestDispatchEventAlerts:
    @pytest.mark.asyncio
    async def test_sends_error_messages(self, dispatcher):
        errors = [("BTC/USDT", "⚠️ 데이터 수신 실패")]
        await dispatcher.dispatch_event_alerts(results=[], errors=errors)
        dispatcher._notifier.send_message.assert_called_once_with("⚠️ 데이터 수신 실패")

    @pytest.mark.asyncio
    async def test_sends_emergency_alert(self, dispatcher):
        result = _make_result(score=85.0, alert_level="EMERGENCY")
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        dispatcher._notifier.send_message.assert_called_once()
        msg = dispatcher._notifier.send_message.call_args[0][0]
        assert "긴급" in msg or "🚨" in msg

    @pytest.mark.asyncio
    async def test_no_emergency_below_threshold(self, dispatcher):
        result = _make_result(score=70.0, alert_level="HIGH")
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        dispatcher._notifier.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_whale_alert(self, dispatcher):
        result = _make_result(score=50.0, whale_alert=True)
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        dispatcher._notifier.send_message.assert_called_once()
        msg = dispatcher._notifier.send_message.call_args[0][0]
        assert "고래" in msg or "🐋" in msg

    @pytest.mark.asyncio
    async def test_no_whale_alert_when_false(self, dispatcher):
        result = _make_result(score=50.0, whale_alert=False)
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        dispatcher._notifier.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_triggered_by_alert_score_not_final_score(self, dispatcher):
        # final_score가 낮아도 alert_score(기술적)가 임계값 이상이면 긴급 알림 발송
        result = _make_result(score=50.0, alert_score=85.0, alert_level="MEDIUM")
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        dispatcher._notifier.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_emergency_when_alert_score_below_threshold(self, dispatcher):
        # final_score가 높아도 alert_score(기술적)가 임계값 미만이면 긴급 알림 없음
        result = _make_result(score=90.0, alert_score=70.0, alert_level="EMERGENCY")
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        dispatcher._notifier.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_cooldown_prevents_duplicate(self, dispatcher):
        result = _make_result(score=85.0, alert_level="EMERGENCY")
        results = [("BTC/USDT", result)]
        # First call — alert sent
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        assert dispatcher._notifier.send_message.call_count == 1
        # Second call — cooldown active, no additional alert
        await dispatcher.dispatch_event_alerts(results=results, errors=[])
        assert dispatcher._notifier.send_message.call_count == 1


class TestDispatchPeriodicReport:
    @pytest.mark.asyncio
    async def test_sends_periodic_report(self, dispatcher):
        result = _make_result(score=50.0)
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_periodic_report(results=results, errors=[])
        dispatcher._notifier.send_message.assert_called_once()
        msg = dispatcher._notifier.send_message.call_args[0][0]
        assert "변동성 분석 리포트" in msg

    @pytest.mark.asyncio
    async def test_sends_report_per_symbol(self, dispatcher):
        results = [
            ("BTC/USDT", _make_result(score=60.0)),
            ("ETH/USDT", _make_result(score=40.0)),
        ]
        await dispatcher.dispatch_periodic_report(results=results, errors=[])
        assert dispatcher._notifier.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_report_also_sends_emergency(self, dispatcher):
        result = _make_result(score=85.0, alert_level="EMERGENCY")
        results = [("BTC/USDT", result)]
        await dispatcher.dispatch_periodic_report(results=results, errors=[])
        # 1 periodic report + 1 emergency alert = 2 messages
        assert dispatcher._notifier.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_report_sends_errors(self, dispatcher):
        errors = [("BTC/USDT", "⚠️ 데이터 오류")]
        await dispatcher.dispatch_periodic_report(results=[], errors=errors)
        dispatcher._notifier.send_message.assert_called_once_with("⚠️ 데이터 오류")
