"""ExchangeRate API — USD/KRW 환율."""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)


@cached(ttl=3600, key_prefix="exchange_rate_usd_krw")
async def fetch_usd_krw() -> float | None:
    """USD/KRW 환율."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
            resp.raise_for_status()
            return float(resp.json()["rates"]["KRW"])
    except Exception as e:
        logger.error("환율 조회 실패: %s", e)
        return None
