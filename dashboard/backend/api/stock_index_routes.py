"""주식 지수 및 경제뉴스 API 라우터."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.yahoo_finance import fetch_us_market, fetch_index_history
from dashboard.backend.collectors.economic_news import fetch_economic_news

logger = logging.getLogger(__name__)
router = APIRouter()

_INDEX_TICKERS = ["^IXIC", "^KS11", "^KQ11"]
_INDEX_NAMES = {"^IXIC": "NASDAQ", "^KS11": "KOSPI", "^KQ11": "KOSDAQ"}


@router.get("/stock-indices")
async def get_stock_indices():
    """NASDAQ·KOSPI·KOSDAQ 현재가 + 스파크라인."""
    us_market = await fetch_us_market()
    if not us_market:
        return JSONResponse([])
    indices = [
        item for item in us_market
        if item.get("ticker") in _INDEX_TICKERS
    ]
    # _INDEX_TICKERS 순서 유지
    order = {t: i for i, t in enumerate(_INDEX_TICKERS)}
    indices.sort(key=lambda x: order.get(x.get("ticker", ""), 99))
    return JSONResponse(indices)


@router.get("/stock-index-history/{ticker}")
async def get_stock_index_history(ticker: str):
    """지수 30일 종가 히스토리."""
    # ticker URL 인코딩 처리: %5EIXIC → ^IXIC
    history = await fetch_index_history(ticker)
    return JSONResponse({"ticker": ticker, "history": history or []})


@router.get("/economic-news")
async def get_economic_news():
    """경제 뉴스 RSS 최신 6개."""
    news = await fetch_economic_news()
    return JSONResponse(news)
