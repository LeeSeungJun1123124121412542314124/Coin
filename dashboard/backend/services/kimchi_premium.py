"""김치 프리미엄 계산 서비스."""

from __future__ import annotations

import logging

from dashboard.backend.collectors.upbit import fetch_btc_krw
from dashboard.backend.collectors.exchange_rate import fetch_usd_krw

logger = logging.getLogger(__name__)


async def calc_kimchi_premium(binance_btc_usd: float) -> dict | None:
    """
    김치 프리미엄 계산.

    김프 = (업비트 BTC원화 / 환율 / 바이낸스 BTC달러 - 1) × 100
    양수 = 한국이 더 비쌈 (국내 과열)
    """
    upbit_krw, usd_krw = await _gather(fetch_btc_krw(), fetch_usd_krw())

    if upbit_krw is None or usd_krw is None or binance_btc_usd <= 0:
        return None

    upbit_usd = upbit_krw / usd_krw
    kimchi_pct = (upbit_usd / binance_btc_usd - 1) * 100

    return {
        "kimchi_premium_pct": round(kimchi_pct, 2),
        "upbit_btc_krw": upbit_krw,
        "upbit_btc_usd": round(upbit_usd, 2),
        "usd_krw": round(usd_krw, 2),
    }


async def _gather(*coros):
    import asyncio
    return await asyncio.gather(*coros)
