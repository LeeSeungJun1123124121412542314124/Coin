"""Bybit V5 공개 API — OI, FR (Binance 451 대체).

Railway US 서버에서는 api.bybit.com이 차단되므로 EU/아시아 리전 필요.
"""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://api.bybit.com"

# 모듈 레벨 httpx 클라이언트 — TCP/TLS 연결 재사용
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


@cached(ttl=60, key_prefix="bybit_oi_current")
async def fetch_open_interest(symbol: str = "BTCUSDT") -> dict | None:
    """미결제약정(OI) 현재값."""
    try:
        client = _get_client()
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
        client = _get_client()
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
        client = _get_client()
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
        client = _get_client()
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


@cached(ttl=300, key_prefix="bybit_oi_change")
async def fetch_oi_change(symbol: str = "BTCUSDT") -> dict | None:
    """OI 1h/24h 변화율 계산.

    fetch_oi_history의 1d 히스토리를 사용해 24h 변화율을,
    5min 간격 OI를 별도 조회해 1h 변화율을 계산한다.

    Returns:
        {
            "change_1h_pct": float | None,
            "change_24h_pct": float | None,
            "current_oi": float | None,
        }
    """
    try:
        client = _get_client()

        # 5min 간격 최근 13봉 조회 (약 1시간 전 값 확보)
        resp_5m = await client.get(
            f"{_BASE}/v5/market/open-interest",
            params={
                "category": "linear",
                "symbol": symbol,
                "intervalTime": "5min",
                "limit": 13,
            },
        )
        resp_5m.raise_for_status()
        items_5m = resp_5m.json().get("result", {}).get("list", [])

        current_oi = None
        oi_1h_ago = None
        if len(items_5m) >= 13:
            current_oi = float(items_5m[0]["openInterest"])
            oi_1h_ago = float(items_5m[-1]["openInterest"])

        change_1h_pct = None
        if current_oi is not None and oi_1h_ago and oi_1h_ago != 0:
            change_1h_pct = round((current_oi - oi_1h_ago) / oi_1h_ago * 100, 2)

        # 1일 히스토리 — 24h 변화율
        resp_1d = await client.get(
            f"{_BASE}/v5/market/open-interest",
            params={
                "category": "linear",
                "symbol": symbol,
                "intervalTime": "1d",
                "limit": 2,
            },
        )
        resp_1d.raise_for_status()
        items_1d = resp_1d.json().get("result", {}).get("list", [])

        change_24h_pct = None
        if len(items_1d) >= 2:
            oi_now = float(items_1d[0]["openInterest"])
            oi_24h = float(items_1d[1]["openInterest"])
            if oi_24h != 0:
                change_24h_pct = round((oi_now - oi_24h) / oi_24h * 100, 2)
            if current_oi is None:
                current_oi = oi_now

        return {
            "symbol": symbol,
            "current_oi": current_oi,
            "change_1h_pct": change_1h_pct,
            "change_24h_pct": change_24h_pct,
        }
    except Exception as e:
        logger.error("OI 변화율 조회 실패 (%s): %s", symbol, e)
        return None
