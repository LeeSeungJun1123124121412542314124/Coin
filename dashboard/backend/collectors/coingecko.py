"""CoinGecko — 코인 가격 6종 + 글로벌 시장 데이터."""

from __future__ import annotations

import os
import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("COINGECKO_API_KEY", "")
_BASE = "https://api.coingecko.com/api/v3"

_COIN_IDS = [
    "bitcoin",
    "ethereum",
    "solana",
    "hyperliquid",
    "injective-protocol",
    "ondo-finance",
]

_COIN_SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "hyperliquid": "HYPE",
    "injective-protocol": "INJ",
    "ondo-finance": "ONDO",
}


@cached(ttl=60, key_prefix="coingecko_prices")
async def fetch_prices() -> dict | None:
    """6개 코인 가격 + 24h 변동률 + 시총 조회."""
    params = {
        "ids": ",".join(_COIN_IDS),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_market_cap": "true",
        "x_cg_demo_api_key": _API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/simple/price", params=params)
            resp.raise_for_status()
            data = resp.json()

        result = []
        for coin_id in _COIN_IDS:
            d = data.get(coin_id, {})
            result.append({
                "id": coin_id,
                "symbol": _COIN_SYMBOLS.get(coin_id, coin_id.upper()),
                "price": d.get("usd"),
                "change_24h": d.get("usd_24h_change"),
                "market_cap": d.get("usd_market_cap"),
            })
        return result
    except Exception as e:
        logger.error("CoinGecko 가격 조회 실패: %s", e)
        return None


@cached(ttl=300, key_prefix="coingecko_global")
async def fetch_global() -> dict | None:
    """전체 시총, BTC 도미넌스 조회."""
    params = {"x_cg_demo_api_key": _API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/global", params=params)
            resp.raise_for_status()
            data = resp.json().get("data", {})

        return {
            "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
            "btc_dominance": data.get("market_cap_percentage", {}).get("btc"),
            "market_cap_change_24h": data.get("market_cap_change_percentage_24h_usd"),
        }
    except Exception as e:
        logger.error("CoinGecko 글로벌 조회 실패: %s", e)
        return None
