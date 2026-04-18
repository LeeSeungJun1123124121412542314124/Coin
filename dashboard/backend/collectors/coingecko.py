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
    try:
        # DB에서 현재 슬롯 목록 동적 조회
        slots = get_slots()
        if not slots:
            logger.warning("coin_slots 테이블이 비어있음 — 가격 조회 스킵")
            return []

        ids_param = ",".join(s["coin_id"] for s in slots)

        params = {
            "vs_currency": "usd",
            "ids": ids_param,
            "x_cg_demo_api_key": _API_KEY,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/coins/markets", params=params)
            resp.raise_for_status()
            data = resp.json()

        by_id = {item["id"]: item for item in data}
        result = []
        for slot in slots:
            coin_id = slot["coin_id"]
            d = by_id.get(coin_id, {})
            result.append({
                "id": coin_id,
                "symbol": slot["symbol"],
                "position": slot["position"],
                "tv_symbol": slot.get("tv_symbol"),
                "price": d.get("current_price"),
                "change_24h": d.get("price_change_percentage_24h"),
                "market_cap": d.get("market_cap"),
                "high_24h": d.get("high_24h"),
                "low_24h": d.get("low_24h"),
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
    if not query or not query.strip():
        return None

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
            "eth_dominance": data.get("market_cap_percentage", {}).get("eth"),
            "market_cap_change_24h": data.get("market_cap_change_percentage_24h_usd"),
        }
    except Exception as e:
        logger.error("CoinGecko 글로벌 조회 실패: %s", e)
        return None


@cached(ttl=900, key_prefix="coingecko_marketcap_chart")
async def fetch_market_cap_chart(days: int = 1) -> list[dict] | None:
    """전체 시총 시계열. Pro 전용일 경우 BTC 기반 근사 폴백.

    폴백은 btc_dominance를 현재 단일값으로 전체 구간에 적용하므로 days > 1 구간에서는 오차가 커질 수 있음.
    """
    params = {"vs_currency": "usd", "days": days, "x_cg_demo_api_key": _API_KEY}
    # 1차: /global/market_cap_chart (Pro일 수도)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/global/market_cap_chart", params=params)
            # raise_for_status() 대신 수동 체크 — Pro 전용(401/403) 시 폴백 진행, 429 시 즉시 종료
            if resp.status_code == 200:
                pairs = resp.json().get("market_cap_chart", {}).get("market_cap", [])
                if pairs:  # 빈 배열이면 폴백 시도
                    return [{"t": int(t), "v": float(v)} for t, v in pairs]
            elif resp.status_code == 429:
                logger.warning("전체 시총 차트 rate limit — 폴백 스킵")
                return None
            logger.info("전체 시총 차트 비-200 응답 %d, 폴백 시도", resp.status_code)
    except Exception as e:
        logger.warning("전체 시총 차트 직접 조회 실패(폴백 시도): %s", e)

    # 2차 폴백: BTC 시총 / btc_dominance × 100
    try:
        g = await fetch_global()
        btc_dom = g.get("btc_dominance") if g else None
        if btc_dom is None:
            return None
        if btc_dom == 0.0:
            logger.warning("btc_dominance가 0 — 폴백 계산 불가")
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE}/coins/bitcoin/market_chart",
                params={"vs_currency": "usd", "days": days, "x_cg_demo_api_key": _API_KEY},
            )
            resp.raise_for_status()
            caps = resp.json().get("market_caps", [])
        return [{"t": int(t), "v": float(v) * 100.0 / btc_dom} for t, v in caps]
    except Exception as e:
        logger.error("전체 시총 차트 폴백 실패: %s", e)
        return None
