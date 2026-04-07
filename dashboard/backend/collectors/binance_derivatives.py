"""Binance 선물 API — OI, FR, 롱숏 비율."""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_FAPI = "https://fapi.binance.com"


@cached(ttl=60, key_prefix="binance_oi_current")
async def fetch_open_interest(symbol: str = "BTCUSDT") -> dict | None:
    """미결제약정(OI) 현재값."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_FAPI}/fapi/v1/openInterest", params={"symbol": symbol})
            resp.raise_for_status()
            data = resp.json()
        return {
            "symbol": symbol,
            "open_interest": float(data["openInterest"]),
        }
    except Exception as e:
        logger.error("OI 조회 실패 (%s): %s", symbol, e)
        return None


@cached(ttl=3600, key_prefix="binance_oi_hist")
async def fetch_oi_history(symbol: str = "BTCUSDT", limit: int = 500) -> list | None:
    """OI 히스토리 (일별, 최대 500일)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_FAPI}/futures/data/openInterestHist",
                params={"symbol": symbol, "period": "1d", "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "timestamp": int(d["timestamp"]),
                "open_interest": float(d["sumOpenInterest"]),
                "open_interest_usd": float(d.get("sumOpenInterestValue", 0)),
            }
            for d in data
        ]
    except Exception as e:
        logger.error("OI 히스토리 조회 실패 (%s): %s", symbol, e)
        return None


@cached(ttl=60, key_prefix="binance_fr_current")
async def fetch_funding_rate(symbol: str = "BTCUSDT", limit: int = 3) -> dict | None:
    """펀딩레이트 최근값 (일별 평균)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_FAPI}/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

        rates = [float(d["fundingRate"]) for d in data]
        avg = sum(rates) / len(rates) if rates else 0
        return {
            "symbol": symbol,
            "funding_rate": round(avg, 6),
            "funding_rate_pct": round(avg * 100, 4),
            "latest_rates": rates,
        }
    except Exception as e:
        logger.error("FR 조회 실패 (%s): %s", symbol, e)
        return None


@cached(ttl=3600, key_prefix="binance_fr_hist")
async def fetch_fr_history(symbol: str = "BTCUSDT", limit: int = 1500) -> list | None:
    """FR 히스토리 (최대 1500건 ≈ 500일)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_FAPI}/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "timestamp": int(d["fundingTime"]),
                "funding_rate": float(d["fundingRate"]),
            }
            for d in data
        ]
    except Exception as e:
        logger.error("FR 히스토리 조회 실패 (%s): %s", symbol, e)
        return None


@cached(ttl=60, key_prefix="binance_longshort")
async def fetch_long_short_ratio(symbol: str = "BTCUSDT") -> dict | None:
    """글로벌 롱/숏 계정 비율."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_FAPI}/futures/data/globalLongShortAccountRatio",
                params={"symbol": symbol, "period": "1h", "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data:
            return None
        d = data[0]
        return {
            "symbol": symbol,
            "long_short_ratio": float(d["longShortRatio"]),
            "long_account": float(d["longAccount"]),
            "short_account": float(d["shortAccount"]),
        }
    except Exception as e:
        logger.error("롱숏 비율 조회 실패 (%s): %s", symbol, e)
        return None
