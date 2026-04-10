"""Notification dispatcher — decoupled from analysis pipeline.

알림 체계 (백테스트 기반, 정밀도 우선):
  CONFIRMED_HIGH   — 기술적 HIGH + OI/FR 파생상품 확인. 92% 정밀도. 쿨다운 2h
  HIGH             — 기술적 HIGH 단독. 75% 정밀도. 쿨다운 4h
  LIQUIDATION_RISK — 기술적 LOW + OI+FR 동시 극단. 신규. 쿨다운 6h
  WHALE            — 온체인 고래 감지. 쿨다운 1h (기존 유지)
  PERIODIC_REPORT  — 12시간 스케줄 발송 (항상)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
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


def _get_db():
    """대시보드 DB 컨텍스트 매니저 (선택적 임포트 — 봇 단독 실행 시 실패 허용)."""
    from dashboard.backend.db.connection import get_db
    return get_db()


class AlertCooldown:
    """알림 중복 전송 방지 — DB 기반 쿨다운 (서버 재시작 후에도 유지)."""

    def is_active(self, key: str, cooldown_type: str = "high") -> bool:
        """DB에서 last_alerted 조회 후 쿨다운 여부 반환."""
        seconds = _COOLDOWNS.get(cooldown_type, 3600.0)
        try:
            with _get_db() as conn:
                row = conn.execute(
                    "SELECT last_alerted FROM alert_cooldowns WHERE key = ?", (key,)
                ).fetchone()
            if row is None:
                return False
            last = datetime.fromisoformat(row[0])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - last).total_seconds() < seconds
        except Exception as e:
            logger.warning("쿨다운 DB 조회 실패 (폴백: 비활성): %s", e)
            return False

    def set(self, key: str, cooldown_type: str = "high") -> None:
        """DB에 UPSERT — last_alerted 갱신."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with _get_db() as conn:
                conn.execute(
                    """INSERT INTO alert_cooldowns (key, last_alerted, cooldown_type)
                       VALUES (?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET
                           last_alerted = excluded.last_alerted,
                           cooldown_type = excluded.cooldown_type""",
                    (key, now, cooldown_type),
                )
        except Exception as e:
            logger.warning("쿨다운 DB 저장 실패: %s", e)


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

        ctx = await self._collect_dashboard_context()
        for symbol, result in results:
            report = self._formatter.periodic_report(symbol, result, dashboard_ctx=ctx)
            await self._notifier.send_message(report)

    async def _send_errors(self, errors: AnalysisErrors) -> None:
        for _symbol, error_msg in errors:
            await self._notifier.send_message(error_msg)

    async def _collect_dashboard_context(self) -> dict:
        """대시보드 시장 컨텍스트 수집 — 알림 포맷에 포함할 데이터."""
        import asyncio
        ctx: dict = {}
        try:
            from dashboard.backend.collectors.coingecko import fetch_stablecoin_caps
            from dashboard.backend.collectors.blockchain_info import fetch_hashrate
            from dashboard.backend.collectors.bybit_derivatives import fetch_oi_change
            from dashboard.backend.collectors.coinbase import fetch_btc_usd
            from dashboard.backend.services.kimchi_premium import calc_kimchi_premium

            btc_usd, stablecoins, hashrate, oi_change = await asyncio.gather(
                fetch_btc_usd(),
                fetch_stablecoin_caps(),
                fetch_hashrate(),
                fetch_oi_change("BTCUSDT"),
                return_exceptions=True,
            )

            if not isinstance(btc_usd, Exception) and btc_usd:
                kimchi = await calc_kimchi_premium(btc_usd)
                if kimchi:
                    ctx["kimchi_pct"] = kimchi.get("kimchi_premium_pct")

            if not isinstance(stablecoins, Exception):
                ctx["stablecoins"] = stablecoins
            if not isinstance(hashrate, Exception) and hashrate:
                ctx["hashrate_eh"] = hashrate.get("hashrate_eh")
            if not isinstance(oi_change, Exception) and oi_change:
                ctx["oi_change_24h_pct"] = oi_change.get("change_24h_pct")
        except Exception as e:
            logger.warning("대시보드 컨텍스트 수집 실패 (알림은 정상 발송): %s", e)
        return ctx

    async def _check_high_alerts(self, symbol: str, result: AggregatedResult) -> None:
        """CONFIRMED_HIGH / HIGH / LIQUIDATION_RISK 순서로 체크."""
        level = result.alert_level

        if level == "CONFIRMED_HIGH":
            key = f"{symbol}:confirmed_high"
            if not self._cooldown.is_active(key, "confirmed_high"):
                ctx = await self._collect_dashboard_context()
                msg = self._formatter.confirmed_high_alert(symbol, result, dashboard_ctx=ctx)
                await self._notifier.send_message(msg)
                self._cooldown.set(key, "confirmed_high")
                _save_alert_history(symbol, level, result)

        elif level == "HIGH":
            key = f"{symbol}:high"
            if not self._cooldown.is_active(key, "high"):
                ctx = await self._collect_dashboard_context()
                msg = self._formatter.high_alert(symbol, result, dashboard_ctx=ctx)
                await self._notifier.send_message(msg)
                self._cooldown.set(key, "high")
                _save_alert_history(symbol, level, result)

        elif level == "LIQUIDATION_RISK":
            key = f"{symbol}:liquidation_risk"
            if not self._cooldown.is_active(key, "liquidation_risk"):
                ctx = await self._collect_dashboard_context()
                msg = self._formatter.liquidation_risk_alert(symbol, result, dashboard_ctx=ctx)
                await self._notifier.send_message(msg)
                self._cooldown.set(key, "liquidation_risk")
                _save_alert_history(symbol, level, result)

    async def _check_whale(self, symbol: str, result: AggregatedResult) -> None:
        if result.whale_alert:
            key = f"{symbol}:whale"
            if not self._cooldown.is_active(key, "whale"):
                msg = self._formatter.whale_alert(symbol, result)
                await self._notifier.send_message(msg)
                self._cooldown.set(key, "whale")
                _save_alert_history(symbol, "WHALE", result)


def _save_alert_history(symbol: str, alert_level: str, result: "AggregatedResult") -> None:
    """알림 발송 이력을 alert_history 테이블에 저장."""
    try:
        details = getattr(result, "details", {})
        with _get_db() as conn:
            conn.execute(
                """INSERT INTO alert_history
                   (symbol, alert_level, alert_score, final_score, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    symbol,
                    alert_level,
                    getattr(result, "alert_score", None),
                    getattr(result, "final_score", None),
                    json.dumps(details) if details else None,
                ),
            )
    except Exception as e:
        logger.warning("알림 히스토리 저장 실패: %s", e)
