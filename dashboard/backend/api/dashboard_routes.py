"""GET /api/dashboard — 탭 1 메인 대시보드 데이터."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.coingecko import fetch_prices, fetch_global
from dashboard.backend.collectors.yahoo_finance import fetch_us_market
from dashboard.backend.collectors.bybit_derivatives import (
    fetch_open_interest,
    fetch_funding_rate,
    fetch_long_short_ratio,
)
from dashboard.backend.collectors.coinbase import fetch_btc_usd
from dashboard.backend.services.kimchi_premium import calc_kimchi_premium

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard")
async def get_dashboard():
    """탭 1 대시보드 전체 데이터 반환."""

    # 모든 데이터 병렬 조회
    (
        coins,
        global_data,
        us_market,
        oi,
        fr,
        long_short,
        coinbase_btc,
    ) = await asyncio.gather(
        fetch_prices(),
        fetch_global(),
        fetch_us_market(),
        fetch_open_interest("BTCUSDT"),
        fetch_funding_rate("BTCUSDT"),
        fetch_long_short_ratio("BTCUSDT"),
        fetch_btc_usd(),
        return_exceptions=True,
    )

    # 예외 발생한 항목은 None으로 처리
    coins = None if isinstance(coins, Exception) else coins
    global_data = None if isinstance(global_data, Exception) else global_data
    us_market = None if isinstance(us_market, Exception) else us_market
    oi = None if isinstance(oi, Exception) else oi
    fr = None if isinstance(fr, Exception) else fr
    long_short = None if isinstance(long_short, Exception) else long_short
    coinbase_btc = None if isinstance(coinbase_btc, Exception) else coinbase_btc

    # BTC 가격 (코인 목록에서 추출)
    btc_price = None
    if coins:
        btc = next((c for c in coins if c["symbol"] == "BTC"), None)
        btc_price = btc["price"] if btc else None

    # 봇의 Fear & Greed (기존 DataCollector 재활용)
    fear_greed = await _get_fear_greed()

    # 김치 프리미엄 (BTC 바이낸스 가격 필요)
    kimchi = None
    if btc_price:
        kimchi = await calc_kimchi_premium(btc_price)

    # 온체인 데이터 (봇의 DataCollector 재활용)
    onchain = await _get_onchain()

    return JSONResponse({
        "coins": coins,
        "global": global_data,
        "us_market": us_market,
        "derivatives": {
            "open_interest": oi,
            "funding_rate": fr,
            "long_short": long_short,
        },
        "coinbase_btc": coinbase_btc,
        "kimchi": kimchi,
        "fear_greed": fear_greed,
        "onchain": onchain,
    })


async def _get_fear_greed() -> dict | None:
    """봇의 DataCollector.fetch_fear_greed() 재활용."""
    from app.data.data_collector import DataCollector

    try:
        collector = DataCollector()
        value = await collector.fetch_fear_greed()
        if value is None:
            return None
        label = _fear_greed_label(value)
        return {"value": value, "label": label}
    except Exception as e:
        logger.error("Fear & Greed 조회 실패: %s", e)
        return None


def _fear_greed_label(value: int) -> str:
    if value <= 25:
        return "극단적 공포"
    if value <= 50:
        return "공포"
    if value <= 75:
        return "탐욕"
    return "극단적 탐욕"


async def _get_onchain() -> dict | None:
    """봇의 DataCollector.fetch_onchain_data() 재활용."""
    from app.data.data_collector import DataCollector

    try:
        collector = DataCollector()
        data = await collector.fetch_onchain_data("btc")
        return data
    except Exception as e:
        logger.error("온체인 조회 실패: %s", e)
        return None
