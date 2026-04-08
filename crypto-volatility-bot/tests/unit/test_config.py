"""Tests for app.utils.config — Config loading from environment variables."""

import pytest

from app.utils.config import Config


class TestConfigFromEnv:
    """Config.from_env() behavior."""

    def test_loads_required_fields(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

        config = Config.from_env()

        assert config.telegram_bot_token == "test-token"
        assert config.telegram_chat_id == "123456"

    def test_raises_on_missing_telegram_bot_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            Config.from_env()

    def test_raises_on_missing_telegram_chat_id(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            Config.from_env()

    def test_default_symbols(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.delenv("SYMBOLS", raising=False)

        config = Config.from_env()

        assert config.symbols == ["BTC/USDT", "ETH/USDT"]

    def test_custom_symbols(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("SYMBOLS", "BTC/USDT,SOL/USDT")

        config = Config.from_env()

        assert config.symbols == ["BTC/USDT", "SOL/USDT"]

    def test_default_analysis_weights(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")

        config = Config.from_env()

        assert config.analysis_weights == {
            "onchain": 0.40,
            "technical": 0.35,
            "sentiment": 0.25,
        }

    def test_weights_sum_to_one(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("WEIGHT_ONCHAIN", "0.50")
        monkeypatch.setenv("WEIGHT_TECHNICAL", "0.30")
        monkeypatch.setenv("WEIGHT_SENTIMENT", "0.20")

        config = Config.from_env()
        total = sum(config.analysis_weights.values())

        assert abs(total - 1.0) < 1e-9

    def test_raises_on_invalid_weights(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("WEIGHT_ONCHAIN", "0.50")
        monkeypatch.setenv("WEIGHT_TECHNICAL", "0.50")
        monkeypatch.setenv("WEIGHT_SENTIMENT", "0.50")

        with pytest.raises(ValueError, match="[Ww]eight"):
            Config.from_env()

    def test_default_log_level(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        config = Config.from_env()

        assert config.log_level == "INFO"

    def test_default_emergency_threshold(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")

        config = Config.from_env()

        assert config.emergency_threshold == 80

    def test_optional_binance_keys_default_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

        config = Config.from_env()

        assert config.bybit_api_key is None
        assert config.bybit_api_secret is None
