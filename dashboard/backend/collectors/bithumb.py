"""빗썸 거래량 수집기."""

from __future__ import annotations

import logging

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://api.bithumb.com"


@cached(300, "bithumb_krw_volume")
async def fetch_krw_volume() -> float | None:
    """빗썸 KRW 마켓 24h 거래대금 합계 (단위: 조원).

    Returns None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/public/ticker/ALL_KRW")
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "0000":
            logger.warning("빗썸 API 오류: %s", data.get("message"))
            return None

        tickers = data.get("data", {})
        total = 0.0
        for symbol, info in tickers.items():
            if symbol == "date":
                continue
            try:
                acc_trade = float(info.get("acc_trade_value_24H", 0) or 0)
                total += acc_trade
            except (TypeError, ValueError):
                continue

        return round(total / 1e12, 4)  # 조원 단위

    except Exception as e:
        logger.error("빗썸 거래량 조회 실패: %s", e)
        return None


@cached(60, "bithumb_btc_krw")
async def fetch_btc_krw() -> float | None:
    """빗썸 BTC/KRW 현재가."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/public/ticker/BTC_KRW")
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "0000":
            return None

        return float(data["data"]["closing_price"])

    except Exception as e:
        logger.error("빗썸 BTC 가격 조회 실패: %s", e)
        return None
