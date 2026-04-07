"""Notification dispatcher — decoupled from analysis pipeline.

Two dispatch modes:
  1. Event alerts: emergency + whale alerts sent immediately (hourly trigger)
  2. Periodic report: full analysis report sent every 12 hours (separate trigger)
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.notifiers.message_formatter import MessageFormatter
from app.notifiers.telegram_notifier import TelegramNotifier

if TYPE_CHECKING:
    from app.analyzers.score_aggregator import AggregatedResult
    from app.pipeline import AnalysisErrors, AnalysisResults
    from app.utils.config import Config

logger = logging.getLogger(__name__)

_DEFAULT_COOLDOWN_SECONDS = 3600.0


class AlertCooldown:
    """알림 중복 전송 방지를 위한 쿨다운 관리."""

    def __init__(self, seconds: float = _DEFAULT_COOLDOWN_SECONDS) -> None:
        self._seconds = seconds
        self._timestamps: dict[str, float] = {}

    def is_active(self, key: str) -> bool:
        ts = self._timestamps.get(key)
        if ts is None:
            return False
        return (time.monotonic() - ts) < self._seconds

    def set(self, key: str) -> None:
        self._timestamps[key] = time.monotonic()


class NotificationDispatcher:
    """Handles all Telegram notification dispatch, separated from analysis."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._notifier = TelegramNotifier(
            token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
        )
        self._formatter = MessageFormatter()
        self._cooldown = AlertCooldown()

    async def dispatch_event_alerts(
        self,
        results: AnalysisResults,
        errors: AnalysisErrors,
    ) -> None:
        """Send error notifications and immediate event alerts (emergency/whale).

        Called every hour after analysis completes.
        """
        await self._send_errors(errors)

        for symbol, result in results:
            await self._check_emergency(symbol, result)
            await self._check_whale(symbol, result)

    async def dispatch_periodic_report(
        self,
        results: AnalysisResults,
        errors: AnalysisErrors,
    ) -> None:
        """Send periodic analysis reports and event alerts.

        Called every 12 hours by a separate scheduler trigger.
        """
        await self._send_errors(errors)

        for symbol, result in results:
            report = self._formatter.periodic_report(symbol, result)
            await self._notifier.send_message(report)

            # Also check for events at report time
            await self._check_emergency(symbol, result)
            await self._check_whale(symbol, result)

    async def _send_errors(self, errors: AnalysisErrors) -> None:
        for _symbol, error_msg in errors:
            await self._notifier.send_message(error_msg)

    async def _check_emergency(self, symbol: str, result: AggregatedResult) -> None:
        if result.alert_score >= self._config.emergency_threshold:
            emerg_key = f"{symbol}:emergency"
            if not self._cooldown.is_active(emerg_key):
                msg = self._formatter.emergency_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(emerg_key)

    async def _check_whale(self, symbol: str, result: AggregatedResult) -> None:
        if result.whale_alert:
            whale_key = f"{symbol}:whale"
            if not self._cooldown.is_active(whale_key):
                msg = self._formatter.whale_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(whale_key)
