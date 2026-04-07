"""Coinbase — BTC 현물가 (코인베이스 프리미엄 계산용)."""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)


@cached(ttl=60, key_prefix="coinbase_btc")
async def fetch_btc_usd() -> float | None:
    """BTC 달러가 (Coinbase 현물)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.coinbase.com/v2/prices/BTC-USD/spot")
            resp.raise_for_status()
            return float(resp.json()["data"]["amount"])
    except Exception as e:
        logger.error("Coinbase BTC 조회 실패: %s", e)
        return None
