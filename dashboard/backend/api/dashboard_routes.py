"""GET /api/dashboard — 탭 1 메인 대시보드 데이터."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.coingecko import fetch_prices, fetch_global, fetch_stablecoin_caps, fetch_market_cap_chart
from dashboard.backend.collectors.yahoo_finance import fetch_us_market
from dashboard.backend.collectors.bybit_derivatives import (
    fetch_open_interest,
    fetch_funding_rate,
    fetch_long_short_ratio,
    fetch_oi_change,
)
from dashboard.backend.collectors.coinbase import fetch_btc_usd
from dashboard.backend.collectors.blockchain_info import fetch_hashrate
from dashboard.backend.services.kimchi_premium import calc_kimchi_premium
from dashboard.backend.utils.shared_data import get_fear_greed, get_onchain
from dashboard.backend.db.connection import get_db

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
        stablecoins,
        hashrate,
        oi_change,
        market_cap_chart,
    ) = await asyncio.gather(
        fetch_prices(),
        fetch_global(),
        fetch_us_market(),
        fetch_open_interest("BTCUSDT"),
        fetch_funding_rate("BTCUSDT"),
        fetch_long_short_ratio("BTCUSDT"),
        fetch_btc_usd(),
        fetch_stablecoin_caps(),
        fetch_hashrate(),
        fetch_oi_change("BTCUSDT"),
        fetch_market_cap_chart(),
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
    stablecoins = None if isinstance(stablecoins, Exception) else stablecoins
    hashrate = None if isinstance(hashrate, Exception) else hashrate
    oi_change = None if isinstance(oi_change, Exception) else oi_change
    market_cap_chart = None if isinstance(market_cap_chart, Exception) else market_cap_chart

    # BTC 가격 (코인 목록에서 추출)
    btc_price = None
    if coins:
        btc = next((c for c in coins if c["symbol"] == "BTC"), None)
        btc_price = btc["price"] if btc else None

    # 봇의 Fear & Greed (기존 DataCollector 재활용)
    fear_greed = await get_fear_greed()

    # 김치 프리미엄 (BTC 바이낸스 가격 필요)
    kimchi = None
    if btc_price:
        kimchi = await calc_kimchi_premium(btc_price)

    # 온체인 데이터 (봇의 DataCollector 재활용)
    onchain = await get_onchain()

    # 김치 프리미엄 히스토리 (최근 7일, DB에서 조회)
    kimchi_history = _get_kimchi_history(days=7)

    # 글로벌 데이터에 시총 차트 병합 (market_cap_chart가 None이면 null로 직렬화됨 — 프론트에서 null 처리 필요)
    # global_data가 None(fetch 실패)이면 market_cap_chart도 응답에서 누락되는 것은 의도된 동작
    if global_data:
        global_data["market_cap_chart"] = market_cap_chart

    return JSONResponse({
        "coins": coins,
        "global": global_data,
        "us_market": us_market,
        "derivatives": {
            "open_interest": oi,
            "funding_rate": fr,
            "long_short": long_short,
            "oi_change": oi_change,
        },
        "coinbase_btc": coinbase_btc,
        "kimchi": kimchi,
        "kimchi_history": kimchi_history,
        "fear_greed": fear_greed,
        "onchain": onchain,
        "stablecoins": stablecoins,
        "hashrate": hashrate,
    })


def _get_kimchi_history(days: int = 7) -> list:
    """kimchi_premium_history 테이블에서 최근 N일 데이터 반환."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT timestamp, btc_krw, btc_usd, usd_krw, premium_pct
                   FROM kimchi_premium_history
                   WHERE timestamp >= datetime('now', ?)
                   ORDER BY timestamp ASC""",
                (f"-{days} days",),
            ).fetchall()
        return [
            {
                "timestamp": row[0],
                "btc_krw": row[1],
                "btc_usd": row[2],
                "usd_krw": row[3],
                "premium_pct": row[4],
            }
            for row in rows
        ]
    except Exception:
        return []
