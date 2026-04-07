"""업비트 — KRW 전체 거래대금, BTC 원화가."""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://api.upbit.com/v1"
_CHUNK_SIZE = 100  # 한 번에 조회 가능한 마켓 수


@cached(ttl=300, key_prefix="upbit_volume")
async def fetch_krw_volume() -> dict | None:
    """KRW 전체 마켓 24h 거래대금 합산 (조 원 단위)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 1. KRW 마켓 목록
            resp = await client.get(f"{_BASE}/market/all", params={"isDetails": "false"})
            resp.raise_for_status()
            krw_markets = [m["market"] for m in resp.json() if m["market"].startswith("KRW-")]

            # 2. 청크로 티커 조회
            total_krw = 0.0
            for i in range(0, len(krw_markets), _CHUNK_SIZE):
                chunk = krw_markets[i:i + _CHUNK_SIZE]
                r = await client.get(
                    f"{_BASE}/ticker",
                    params={"markets": ",".join(chunk)},
                )
                r.raise_for_status()
                for t in r.json():
                    total_krw += float(t.get("acc_trade_price_24h") or 0)

        return {
            "total_krw": total_krw,
            "total_trillion": round(total_krw / 1e12, 2),
        }
    except Exception as e:
        logger.error("업비트 거래량 조회 실패: %s", e)
        return None


@cached(ttl=60, key_prefix="upbit_btc_krw")
async def fetch_btc_krw() -> float | None:
    """BTC 원화가 (김치프리미엄 계산용)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/ticker", params={"markets": "KRW-BTC"})
            resp.raise_for_status()
            data = resp.json()
        return float(data[0]["trade_price"])
    except Exception as e:
        logger.error("업비트 BTC 조회 실패: %s", e)
        return None
