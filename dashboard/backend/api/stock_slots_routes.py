"""주식 슬롯 관리 + 현재가 API 라우터."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend import cache
from dashboard.backend.collectors.naver_finance import fetch_naver_ohlcv, search_naver_stocks
from dashboard.backend.collectors.yahoo_finance import (
    fetch_stock_ohlcv,
    fetch_stock_prices,
    lookup_stock_info,
    search_stocks,
)
from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# Yahoo Finance exchangeName → TradingView 거래소 코드 매핑
_EXCHANGE_MAP = {
    "NasdaqGS": "NASDAQ",
    "NasdaqCM": "NASDAQ",
    "NasdaqGM": "NASDAQ",
    "NYQ": "NYSE",
    "NYSEArca": "NYSE",
    "NYSEAmerican": "AMEX",
}


class StockSlotUpdateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)


def _get_slots(market: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT position, ticker, name, tv_symbol FROM stock_slots WHERE market=? ORDER BY position",
            (market,),
        ).fetchall()
    return [{"position": r[0], "ticker": r[1], "name": r[2], "tv_symbol": r[3]} for r in rows]


def _update_slot(market: str, position: int, ticker: str, name: str, tv_symbol: str | None) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE stock_slots SET ticker=?, name=?, tv_symbol=? WHERE market=? AND position=?",
            (ticker, name, tv_symbol, market, position),
        )


@router.get("/stock-search")
async def get_stock_search(q: str, market: str):
    if market not in ("kr", "us"):
        raise HTTPException(status_code=400, detail="market must be kr or us")
    if not q or not q.strip():
        return []
    # kr 마켓은 네이버 검색(한글 지원), us 마켓은 Yahoo 검색
    if market == "kr":
        results = await search_naver_stocks(q.strip())
    else:
        results = await search_stocks(q.strip(), market)
    return results


@router.get("/stock-slots/{market}")
async def get_stock_slots(market: str = Path(..., pattern="^(kr|us)$")):
    return _get_slots(market)


@router.put("/stock-slots/{market}/{position}")
async def put_stock_slot(
    request: StockSlotUpdateRequest,
    market: str = Path(..., pattern="^(kr|us)$"),
    position: int = Path(..., ge=1, le=7),
):
    # ticker 정규화 (공백 제거 + 대문자)
    ticker = request.ticker.strip().upper()

    # 종목 정보 자동 조회
    info = await lookup_stock_info(ticker)
    if info is None:
        raise HTTPException(status_code=422, detail=f"종목을 찾을 수 없습니다: {ticker}")

    name = info["name"]

    # TradingView 심볼 자동 생성
    if market == "kr":
        base_ticker = ticker.split(".")[0]  # "005930.KS" → "005930"
        # 한국 거래소는 TradingView에서 거래소 구분 없이 모두 KRX: prefix 사용
        tv_prefix = "KRX"
        tv_symbol = f"{tv_prefix}:{base_ticker}"
    else:
        exchange_raw = info["exchange"]
        exchange = _EXCHANGE_MAP.get(exchange_raw, exchange_raw)
        tv_symbol = f"{exchange}:{ticker}"

    _update_slot(market, position, ticker, name, tv_symbol)
    cache.delete_prefix("stock_prices")
    return JSONResponse({"market": market, "position": position, "ticker": ticker, "name": name, "tv_symbol": tv_symbol})


@router.get("/stock-prices/{market}")
async def get_stock_prices(market: str = Path(..., pattern="^(kr|us)$")):
    slots = _get_slots(market)
    if not slots:
        return []
    slot_tuples = tuple((s["ticker"], s["name"], s["tv_symbol"]) for s in slots)
    results = await fetch_stock_prices(slot_tuples)
    return results


@router.get("/stock-chart/{ticker}")
async def get_stock_chart(
    ticker: str = Path(...),
    interval: Literal["1d", "1wk", "1mo"] = Query(default="1d"),
):
    """종목 OHLCV 차트 데이터 조회.

    Args:
        ticker: 종목 티커 (예: "AAPL", "005930.KS")
        interval: 조회 간격 ("1d", "1wk", "1mo"), 기본값 "1d"

    Returns:
        [{"date": str, "open": float, "high": float, "low": float, "close": float, "volume": int}]
    """
    # 한국 티커(.KS, .KQ)는 네이버 파이낸스, 그 외는 Yahoo Finance
    is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
    if is_korean:
        result = await fetch_naver_ohlcv(ticker, interval)
        if result is None:
            result = await fetch_stock_ohlcv(ticker, interval)
    else:
        result = await fetch_stock_ohlcv(ticker, interval)
    if result is None:
        return []
    return result
