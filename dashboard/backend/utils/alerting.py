"""잡 실패 시 텔레그램 알림."""
from __future__ import annotations
import logging
import os
import httpx

logger = logging.getLogger(__name__)
_TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

async def notify_job_failure(job_name: str, error: str) -> None:
    """텔레그램으로 잡 실패 알림 발송."""
    if not _TELEGRAM_TOKEN or not _CHAT_ID:
        logger.warning("텔레그램 설정 없음 — 잡 실패 알림 스킵: %s", job_name)
        return
    text = f"⚠️ <b>잡 실패</b>\n잡: {job_name}\n오류: {error}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"},
            )
    except Exception as e:
        logger.error("잡 실패 알림 발송 실패: %s", e)
