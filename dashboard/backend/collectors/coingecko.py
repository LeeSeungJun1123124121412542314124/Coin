"""CoinGecko — 코인 가격 (DB 슬롯 기반 동적 목록) + 글로벌 시장 데이터."""

from __future__ import annotations

import os
import logging
import httpx

from dashboard.backend.cache import cached
from dashboard.backend.db.coin_slots import get_slots

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("COINGECKO_API_KEY", "")
_BASE = "https://api.coingecko.com/api/v3"

# 스테이블코인 시가총액 조회 대상
_STABLECOIN_IDS = ["tether", "usd-coin"]
_STABLECOIN_SYMBOLS = {"tether": "USDT", "usd-coin": "USDC"}


@cached(ttl=60, key_prefix="coingecko_prices")
async def fetch_prices() -> list | None:
    """DB 슬롯 기반 코인 가격 + 24h 변동률 + 시총 조회."""
    # DB에서 현재 슬롯 목록 동적 조회
    slots = get_slots()
    if not slots:
        logger.warning("coin_slots 테이블이 비어있음 — 가격 조회 스킵")
        return []

    coin_id_to_slot = {s["coin_id"]: s for s in slots}
    ids_param = ",".join(coin_id_to_slot.keys())

    params = {
        "ids": ids_param,
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
        for slot in slots:
            coin_id = slot["coin_id"]
            d = data.get(coin_id, {})
            result.append({
                "id": coin_id,
                "symbol": slot["symbol"],
                "position": slot["position"],
                "tv_symbol": slot.get("tv_symbol"),
                "price": d.get("usd"),
                "change_24h": d.get("usd_24h_change"),
                "market_cap": d.get("usd_market_cap"),
            })
        return result
    except Exception as e:
        logger.error("CoinGecko 가격 조회 실패: %s", e)
        return None


async def search_coin(query: str) -> dict | None:
    """CoinGecko에서 코인 검색 후 시총 순위 최상위 1건 반환.

    Args:
        query: 검색어 (코인 이름 또는 심볼)

    Returns:
        {"id": ..., "symbol": ..., "name": ...} 또는 None
    """
    params = {
        "query": query,
        "x_cg_demo_api_key": _API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        coins = data.get("coins", [])
        # market_cap_rank이 None이 아닌 항목만 필터링 후 순위 오름차순 정렬
        ranked = [c for c in coins if c.get("market_cap_rank") is not None]
        if not ranked:
            return None

        ranked.sort(key=lambda c: c["market_cap_rank"])
        top = ranked[0]
        return {
            "id": top.get("id"),
            "symbol": top.get("symbol"),
            "name": top.get("name"),
        }
    except Exception as e:
        logger.error("CoinGecko 코인 검색 실패 (query=%s): %s", query, e)
        return None


async def verify_price(coin_id: str) -> dict | None:
    """특정 코인의 현재 가격과 24h 변동률을 조회해 유효성 확인.

    Args:
        coin_id: CoinGecko 코인 ID

    Returns:
        {"price": ..., "change_24h": ...} 또는 None (코인 ID 무효 / API 오류)
    """
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "x_cg_demo_api_key": _API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/simple/price", params=params)
            resp.raise_for_status()
            data = resp.json()

        coin_data = data.get(coin_id)
        if not coin_data:
            return None

        return {
            "price": coin_data.get("usd"),
            "change_24h": coin_data.get("usd_24h_change"),
        }
    except Exception as e:
        logger.error("CoinGecko 가격 검증 실패 (coin_id=%s): %s", coin_id, e)
        return None


@cached(ttl=300, key_prefix="coingecko_stablecoins")
async def fetch_stablecoin_caps() -> list | None:
    """USDT/USDC 시가총액 + 24h 변화율 조회."""
    params = {
        "ids": ",".join(_STABLECOIN_IDS),
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
        for coin_id in _STABLECOIN_IDS:
            d = data.get(coin_id, {})
            result.append({
                "id": coin_id,
                "symbol": _STABLECOIN_SYMBOLS.get(coin_id, coin_id.upper()),
                "market_cap": d.get("usd_market_cap"),
                "change_24h": d.get("usd_24h_change"),
            })
        return result
    except Exception as e:
        logger.error("스테이블코인 시총 조회 실패: %s", e)
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
