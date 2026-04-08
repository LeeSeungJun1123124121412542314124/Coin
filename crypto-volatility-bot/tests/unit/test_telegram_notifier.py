"""Tests for TelegramNotifier — 5 tests (mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import TelegramError

from app.notifiers.telegram_notifier import TelegramNotifier


@pytest.fixture
def notifier() -> TelegramNotifier:
    with patch("app.notifiers.telegram_notifier.Bot"):
        n = TelegramNotifier(token="fake-token", chat_id="123456")
    return n


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_calls_send_message(self, notifier):
        mock_bot = AsyncMock()
        notifier._bot = mock_bot
        result = await notifier.send_message("Hello")
        mock_bot.send_message.assert_called_once_with(chat_id="123456", text="Hello", parse_mode="HTML")
        assert result is True

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self, notifier):
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = [
            TelegramError("fail"),
            TelegramError("fail"),
            None,
        ]
        notifier._bot = mock_bot
        with patch("app.notifiers.telegram_notifier.asyncio.sleep", new_callable=AsyncMock):
            result = await notifier.send_message("Hello")
        assert mock_bot.send_message.call_count == 3
        assert result is True

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_no_crash(self, notifier):
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = TelegramError("always fails")
        notifier._bot = mock_bot
        with patch("app.notifiers.telegram_notifier.asyncio.sleep", new_callable=AsyncMock):
            result = await notifier.send_message("Hello")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_returns_false_on_failure(self, notifier):
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = TelegramError("always fails")
        notifier._bot = mock_bot
        with patch("app.notifiers.telegram_notifier.asyncio.sleep", new_callable=AsyncMock):
            result = await notifier.send_message("Hello")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_uses_correct_chat_id(self, notifier):
        mock_bot = AsyncMock()
        notifier._bot = mock_bot
        await notifier.send_message("Test")
        _, kwargs = mock_bot.send_message.call_args
        assert kwargs["chat_id"] == "123456"
