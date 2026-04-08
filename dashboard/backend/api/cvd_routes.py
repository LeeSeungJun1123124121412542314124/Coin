"""CVD 스크리너 API 라우터 — 탭 7."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from dashboard.backend.services.cvd_service import (
    run_screener, score_symbol, get_cvd_chart, SCREENER_SYMBOLS,
)
from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/cvd-screener")
async def get_cvd_screener(
    timeframe: str = Query("4h", pattern="^(1h|4h|1d)$"),
):
    """CVD 11팩터 스크리너 전체 종목 결과."""
    results = await run_screener(timeframe)
    return JSONResponse({
        "timeframe": timeframe,
        "results": results,
        "total": len(results),
    })


@router.get("/cvd")
async def get_cvd_detail(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("4h", pattern="^(1h|4h|1d)$"),
    limit: int = Query(100, ge=20, le=500),
):
    """특정 종목 CVD 차트 + 스코어."""
    try:
        loop = asyncio.get_running_loop()
        from app.data.data_collector import DataCollector
        from dashboard.backend.collectors.bybit_derivatives import (
            fetch_open_interest, fetch_funding_rate,
        )

        collector = DataCollector()
        binance_symbol = symbol.replace("/", "")

        df, oi, fr = await asyncio.gather(
            loop.run_in_executor(None, collector.fetch_ohlcv, symbol, timeframe, limit),
            fetch_open_interest(binance_symbol),
            fetch_funding_rate(binance_symbol),
            return_exceptions=True,
        )

        if isinstance(df, Exception) or df is None:
            return JSONResponse({"error": "데이터 조회 실패", "symbol": symbol}, status_code=500)

        fr_val = fr.get("funding_rate") if isinstance(fr, dict) else None

        chart_data = get_cvd_chart(df)
        score_result = score_symbol(df, None, fr_val)

        return JSONResponse({
            "symbol": symbol,
            "timeframe": timeframe,
            "chart": chart_data[-limit:],
            "score": score_result,
        })

    except Exception as e:
        logger.error("CVD 상세 조회 실패 (%s): %s", symbol, e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/cvd-symbols")
async def get_cvd_symbols():
    """스크리너 대상 종목 목록."""
    return JSONResponse({"symbols": SCREENER_SYMBOLS})
