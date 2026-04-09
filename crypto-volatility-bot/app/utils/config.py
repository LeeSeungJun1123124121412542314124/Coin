"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

_REQUIRED = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    bybit_api_key: str | None = None
    bybit_api_secret: str | None = None
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    analysis_weights: dict[str, float] = field(
        default_factory=lambda: {"onchain": 0.40, "technical": 0.35, "sentiment": 0.25}
    )
    log_level: str = "INFO"
    emergency_threshold: int = 80

    @classmethod
    def from_env(cls) -> Config:
        for key in _REQUIRED:
            if not os.getenv(key):
                raise ValueError(f"Missing required environment variable: {key}")

        symbols_raw = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT")
        symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]

        w_onchain = float(os.getenv("WEIGHT_ONCHAIN", "0.40"))
        w_technical = float(os.getenv("WEIGHT_TECHNICAL", "0.35"))
        w_sentiment = float(os.getenv("WEIGHT_SENTIMENT", "0.25"))
        total = w_onchain + w_technical + w_sentiment
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Weights must sum to 1.0 (got {total:.4f}). "
                "Check WEIGHT_ONCHAIN, WEIGHT_TECHNICAL, WEIGHT_SENTIMENT."
            )

        bybit_key = os.getenv("BYBIT_API_KEY") or None
        bybit_secret = os.getenv("BYBIT_API_SECRET") or None

        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),  # type: ignore[arg-type]
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),  # type: ignore[arg-type]
            bybit_api_key=bybit_key,
            bybit_api_secret=bybit_secret,
            symbols=symbols,
            analysis_weights={"onchain": w_onchain, "technical": w_technical, "sentiment": w_sentiment},
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            emergency_threshold=int(os.getenv("EMERGENCY_THRESHOLD", "80")),
        )
