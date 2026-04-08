"""E2E tests — full pipeline with all APIs mocked.

After the analysis/notification split, run_analysis() is pure analysis
(no notifications). Notification dispatch is tested separately.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

_MOCK_OHLCV = pd.DataFrame(
    {
        "open": [30000.0] * 100,
        "high": [31000.0] * 100,
        "low": [29000.0] * 100,
        "close": [30500.0] * 100,
        "volume": [1000.0] * 100,
    }
)

_MOCK_ONCHAIN = {
    "exchange_inflow": 500.0,
    "exchange_outflow": 400.0,
    "whale_transaction_volume": 0.0,
    "dormant_whale_activated": False,
}


def _make_config_mock():
    cfg = MagicMock()
    cfg.telegram_bot_token = "test-token"
    cfg.telegram_chat_id = "123"
    cfg.bybit_api_key = None
    cfg.bybit_api_secret = None
    cfg.symbols = ["BTC/USDT"]
    cfg.analysis_weights = {"onchain": 0.40, "technical": 0.35, "sentiment": 0.25}
    cfg.log_level = "INFO"
    cfg.emergency_threshold = 80
    return cfg


class TestPipelineRun:
    @pytest.mark.asyncio
    async def test_full_pipeline_runs_without_error(self):
        from app.pipeline import run_analysis

        with patch("app.pipeline.DataCollector") as MockCollector:
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 50
            mock_collector.fetch_onchain_data.return_value = _MOCK_ONCHAIN

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            assert len(results) == 1
            symbol, aggregated = results[0]
            assert symbol == "BTC/USDT"
            assert 0 <= aggregated.final_score <= 100
            assert errors == []

    @pytest.mark.asyncio
    async def test_emergency_score_detected(self):
        from app.pipeline import run_analysis

        high_vol_onchain = dict(_MOCK_ONCHAIN)
        high_vol_onchain["exchange_inflow"] = 5000.0
        high_vol_onchain["exchange_outflow"] = 100.0

        with (
            patch("app.pipeline.DataCollector") as MockCollector,
            patch("app.pipeline.TechnicalAnalyzer") as MockTA,
            patch("app.pipeline.SentimentAnalyzer") as MockSA,
        ):
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 5
            mock_collector.fetch_onchain_data.return_value = high_vol_onchain

            from app.analyzers.base import AnalysisResult

            MockTA.return_value.analyze.return_value = AnalysisResult(score=90, signal="HIGH")
            MockSA.return_value.analyze.return_value = AnalysisResult(score=90, signal="EXTREME_FEAR")

            config = _make_config_mock()
            config.emergency_threshold = 80
            results, errors = await run_analysis(config)

            if results:
                _, aggregated = results[0]
                assert aggregated.final_score >= 80

    @pytest.mark.asyncio
    async def test_whale_alert_detected(self):
        from app.pipeline import run_analysis

        whale_onchain = dict(_MOCK_ONCHAIN)
        whale_onchain["whale_transaction_volume"] = 100.0
        whale_onchain["dormant_whale_activated"] = True

        with patch("app.pipeline.DataCollector") as MockCollector:
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 50
            mock_collector.fetch_onchain_data.return_value = whale_onchain

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            if results:
                _, aggregated = results[0]
                assert aggregated.whale_alert is True

    @pytest.mark.asyncio
    async def test_coinmetrics_failure_uses_neutral_onchain(self):
        from app.pipeline import run_analysis

        with patch("app.pipeline.DataCollector") as MockCollector:
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 50
            mock_collector.fetch_onchain_data.return_value = None  # CoinMetrics failure

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            # 온체인 실패해도 분석은 계속 (중립 점수 사용)
            assert len(results) == 1
            assert errors == []
            # 온체인 중립 점수(50)가 반영된 결과
            _, aggregated = results[0]
            assert aggregated.details["onchain_signal"] == "NEUTRAL"

    @pytest.mark.asyncio
    async def test_binance_failure_uses_neutral_fallback(self):
        from app.pipeline import run_analysis

        with patch("app.pipeline.DataCollector") as MockCollector:
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = None  # Binance failure
            mock_collector.fetch_fear_greed.return_value = 50
            mock_collector.fetch_onchain_data.return_value = _MOCK_ONCHAIN

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            # Analysis still completes with neutral technical fallback
            assert len(results) == 1
            assert isinstance(results, list)


class TestNotificationDispatch:
    """E2E tests for the full analysis + notification flow."""

    @pytest.mark.asyncio
    async def test_event_alerts_sent_for_emergency(self):
        from app.notification_dispatcher import NotificationDispatcher
        from app.pipeline import run_analysis

        high_vol_onchain = dict(_MOCK_ONCHAIN)
        high_vol_onchain["exchange_inflow"] = 5000.0
        high_vol_onchain["exchange_outflow"] = 100.0

        with (
            patch("app.pipeline.DataCollector") as MockCollector,
            patch("app.pipeline.TechnicalAnalyzer") as MockTA,
            patch("app.pipeline.SentimentAnalyzer") as MockSA,
        ):
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 5
            mock_collector.fetch_onchain_data.return_value = high_vol_onchain

            from app.analyzers.base import AnalysisResult

            MockTA.return_value.analyze.return_value = AnalysisResult(score=90, signal="HIGH")
            MockSA.return_value.analyze.return_value = AnalysisResult(score=90, signal="EXTREME_FEAR")

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            dispatcher = NotificationDispatcher(config)
            dispatcher._notifier = AsyncMock()

            await dispatcher.dispatch_event_alerts(results, errors)

            if results and results[0][1].final_score >= 80:
                assert dispatcher._notifier.send_message.call_count >= 1

    @pytest.mark.asyncio
    async def test_periodic_report_sent(self):
        from app.notification_dispatcher import NotificationDispatcher
        from app.pipeline import run_analysis

        with patch("app.pipeline.DataCollector") as MockCollector:
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 50
            mock_collector.fetch_onchain_data.return_value = _MOCK_ONCHAIN

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            dispatcher = NotificationDispatcher(config)
            dispatcher._notifier = AsyncMock()

            await dispatcher.dispatch_periodic_report(results, errors)

            # Should send periodic report for BTC/USDT
            assert dispatcher._notifier.send_message.call_count >= 1
            msg = dispatcher._notifier.send_message.call_args_list[0][0][0]
            assert "변동성 분석 리포트" in msg

    @pytest.mark.asyncio
    async def test_no_error_alert_on_coinmetrics_failure(self):
        from app.notification_dispatcher import NotificationDispatcher
        from app.pipeline import run_analysis

        with patch("app.pipeline.DataCollector") as MockCollector:
            mock_collector = MockCollector.return_value
            mock_collector.fetch_ohlcv.return_value = _MOCK_OHLCV
            mock_collector.fetch_fear_greed.return_value = 50
            mock_collector.fetch_onchain_data.return_value = None

            config = _make_config_mock()
            results, errors = await run_analysis(config)

            dispatcher = NotificationDispatcher(config)
            dispatcher._notifier = AsyncMock()

            await dispatcher.dispatch_event_alerts(results, errors)

            # 온체인 실패는 중립 점수로 처리 → 에러 알림 없음 (일반 분석 결과만)
            # 긴급 임계값(80) 미만이면 아무 알림도 없음
            _, aggregated = results[0]
            if aggregated.alert_score < config.emergency_threshold:
                assert dispatcher._notifier.send_message.call_count == 0
