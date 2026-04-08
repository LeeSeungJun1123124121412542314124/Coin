"""Notification dispatcher — decoupled from analysis pipeline.

알림 체계 (백테스트 기반, 정밀도 우선):
  CONFIRMED_HIGH   — 기술적 HIGH + OI/FR 파생상품 확인. 92% 정밀도. 쿨다운 2h
  HIGH             — 기술적 HIGH 단독. 75% 정밀도. 쿨다운 4h
  LIQUIDATION_RISK — 기술적 LOW + OI+FR 동시 극단. 신규. 쿨다운 6h
  WHALE            — 온체인 고래 감지. 쿨다운 1h (기존 유지)
  PERIODIC_REPORT  — 12시간 스케줄 발송 (항상)
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

# 유형별 쿨다운 (초)
_COOLDOWNS = {
    "confirmed_high": 7200.0,    # 2h
    "high": 14400.0,             # 4h
    "liquidation_risk": 21600.0, # 6h
    "whale": 3600.0,             # 1h
}


class AlertCooldown:
    """알림 중복 전송 방지 — 유형별 쿨다운 지원."""

    def __init__(self) -> None:
        self._timestamps: dict[str, float] = {}

    def is_active(self, key: str, cooldown_type: str = "high") -> bool:
        ts = self._timestamps.get(key)
        if ts is None:
            return False
        seconds = _COOLDOWNS.get(cooldown_type, 3600.0)
        return (time.monotonic() - ts) < seconds

    def set(self, key: str) -> None:
        self._timestamps[key] = time.monotonic()


class NotificationDispatcher:
    """Telegram 알림 발송 — 분석 파이프라인과 분리."""

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
        """즉시 이벤트 알림 — 매시간 체크."""
        await self._send_errors(errors)

        for symbol, result in results:
            await self._check_high_alerts(symbol, result)
            await self._check_whale(symbol, result)

    async def dispatch_periodic_report(
        self,
        results: AnalysisResults,
        errors: AnalysisErrors,
    ) -> None:
        """12시간 정기 리포트 발송."""
        await self._send_errors(errors)

        for symbol, result in results:
            report = self._formatter.periodic_report(symbol, result)
            await self._notifier.send_message(report)

    async def _send_errors(self, errors: AnalysisErrors) -> None:
        for _symbol, error_msg in errors:
            await self._notifier.send_message(error_msg)

    async def _check_high_alerts(self, symbol: str, result: AggregatedResult) -> None:
        """CONFIRMED_HIGH / HIGH / LIQUIDATION_RISK 순서로 체크."""
        level = result.alert_level

        if level == "CONFIRMED_HIGH":
            key = f"{symbol}:confirmed_high"
            if not self._cooldown.is_active(key, "confirmed_high"):
                msg = self._formatter.confirmed_high_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(key)

        elif level == "HIGH":
            key = f"{symbol}:high"
            if not self._cooldown.is_active(key, "high"):
                msg = self._formatter.high_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(key)

        elif level == "LIQUIDATION_RISK":
            key = f"{symbol}:liquidation_risk"
            if not self._cooldown.is_active(key, "liquidation_risk"):
                msg = self._formatter.liquidation_risk_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(key)

    async def _check_whale(self, symbol: str, result: AggregatedResult) -> None:
        if result.whale_alert:
            key = f"{symbol}:whale"
            if not self._cooldown.is_active(key, "whale"):
                msg = self._formatter.whale_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(key)
