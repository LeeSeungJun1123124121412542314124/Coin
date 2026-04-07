"""Backtest data loader — historical OHLCV from exchange (ccxt) or CSV."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def from_exchange(
    symbol: str,
    timeframe: str = "4h",
    limit: int = 500,
    exchange_id: str = "bybit",
    api_key: str | None = None,
    api_secret: str | None = None,
) -> pd.DataFrame | None:
    """Fetch historical OHLCV from a ccxt-supported exchange.

    Args:
        symbol: Trading pair, e.g. "BTC/USDT".
        timeframe: Candlestick interval, e.g. "1h", "4h", "1d".
        limit: Number of candles to fetch.
        exchange_id: ccxt exchange id (default: "bybit").
        api_key: Optional API key.
        api_secret: Optional API secret.

    Returns:
        DataFrame with columns [open, high, low, close, volume] or None on failure.
    """
    try:
        import ccxt  # type: ignore
    except ImportError:
        logger.error("ccxt not installed. Run: pip install ccxt")
        return None

    try:
        exchange_cls = getattr(ccxt, exchange_id)
        params: dict[str, Any] = {"enableRateLimit": True}
        if api_key:
            params["apiKey"] = api_key
        if api_secret:
            params["secret"] = api_secret
        exchange = exchange_cls(params)
        raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=_OHLCV_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")
        return df[["open", "high", "low", "close", "volume"]].astype(float)
    except Exception as exc:
        logger.error("Failed to fetch OHLCV from %s: %s", exchange_id, exc)
        return None


def from_csv(path: str | Path) -> pd.DataFrame | None:
    """Load historical OHLCV from a CSV file (offline backtest).

    The CSV must have columns: open, high, low, close, volume.
    An optional timestamp/date column will be used as the index if present.

    Args:
        path: Path to the CSV file.

    Returns:
        DataFrame with OHLCV data or None on failure.
    """
    try:
        df = pd.read_csv(path)
        # Use first column as index if it looks like a date/timestamp
        if df.columns[0].lower() in ("timestamp", "date", "time"):
            df = df.set_index(df.columns[0])
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            logger.error("CSV missing columns: %s", missing)
            return None
        return df[list(required)].astype(float)
    except Exception as exc:
        logger.error("Failed to load CSV %s: %s", path, exc)
        return None
