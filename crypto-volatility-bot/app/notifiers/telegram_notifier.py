"""Telegram notifier with retry logic."""

from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self._chat_id = chat_id
        self._bot = Bot(token=token)

    async def send_message(self, text: str) -> bool:
        """메시지를 전송한다. 성공 시 True, 실패 시 False 반환."""
        for attempt in range(_MAX_RETRIES):
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id, text=text, parse_mode="HTML",
                )
                return True
            except TelegramError as e:
                if attempt == _MAX_RETRIES - 1:
                    logger.error(
                        "텔레그램 메시지 전송 실패 (%d회 시도): %s", _MAX_RETRIES, e
                    )
                    return False
                await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
        return False
