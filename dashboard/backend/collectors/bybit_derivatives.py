"""Bybit V5 공개 API — OI, FR (Binance 451 대체).

Railway US West 서버에서 Binance fapi는 HTTP 451로 차단되므로
동일한 인터페이스를 Bybit V5 API로 구현한다.
"""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://api.bybit.com"


@cached(ttl=60, key_prefix="bybit_oi_current")
async def fetch_open_interest(symbol: str = "BTCUSDT") -> dict | None:
    """미결제약정(OI) 현재값."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE}/v5/market/open-interest",
                params={"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("result", {}).get("list", [])
        if not items:
            return None
        return {
            "symbol": symbol,
            "open_interest": float(items[0]["openInterest"]),
        }
    except Exception as e:
        logger.error("OI 조회 실패 (%s): %s", symbol, e)
        return None


@cached(ttl=3600, key_prefix="bybit_oi_hist")
async def fetch_oi_history(symbol: str = "BTCUSDT", limit: int = 500) -> list | None:
    """OI 히스토리 (일별)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/v5/market/open-interest",
                params={"category": "linear", "symbol": symbol, "intervalTime": "1d", "limit": min(limit, 200)},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("result", {}).get("list", [])
        # Bybit 응답은 최신순 → 역순 정렬
        return [
            {
                "timestamp": int(d["timestamp"]),
                "open_interest": float(d["openInterest"]),
                "open_interest_usd": 0.0,
            }
            for d in reversed(items)
        ]
    except Exception as e:
        logger.error("OI 히스토리 조회 실패 (%s): %s", symbol, e)
        return None


@cached(ttl=60, key_prefix="bybit_fr_current")
async def fetch_funding_rate(symbol: str = "BTCUSDT", limit: int = 3) -> dict | None:
    """펀딩레이트 최근값."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE}/v5/market/funding/history",
                params={"category": "linear", "symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("result", {}).get("list", [])
        if not items:
            return None
        rates = [float(d["fundingRate"]) for d in items]
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


@cached(ttl=3600, key_prefix="bybit_fr_hist")
async def fetch_fr_history(symbol: str = "BTCUSDT", limit: int = 1500) -> list | None:
    """FR 히스토리."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/v5/market/funding/history",
                params={"category": "linear", "symbol": symbol, "limit": min(limit, 200)},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("result", {}).get("list", [])
        return [
            {
                "timestamp": int(d["fundingRateTimestamp"]),
                "funding_rate": float(d["fundingRate"]),
            }
            for d in reversed(items)
        ]
    except Exception as e:
        logger.error("FR 히스토리 조회 실패 (%s): %s", symbol, e)
        return None


async def fetch_long_short_ratio(symbol: str = "BTCUSDT") -> dict | None:
    """롱숏 비율 — Bybit 공개 API에서 제공하지 않으므로 None 반환."""
    return None
