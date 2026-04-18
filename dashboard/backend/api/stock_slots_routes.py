"""주식 슬롯 관리 + 현재가 API 라우터."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend import cache
from dashboard.backend.collectors.yahoo_finance import fetch_stock_prices
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.errors import api_error

logger = logging.getLogger(__name__)
router = APIRouter()


class StockSlotUpdateRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    tv_symbol: str | None = None


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


@router.get("/stock-slots/{market}")
async def get_stock_slots(market: str = Path(..., pattern="^(kr|us)$")):
    return _get_slots(market)


@router.put("/stock-slots/{market}/{position}")
async def put_stock_slot(
    request: StockSlotUpdateRequest,
    market: str = Path(..., pattern="^(kr|us)$"),
    position: int = Path(..., ge=1, le=5),
):
    _update_slot(market, position, request.ticker, request.name, request.tv_symbol)
    cache.delete_prefix("stock_prices")
    return JSONResponse({"market": market, "position": position, "ticker": request.ticker, "name": request.name, "tv_symbol": request.tv_symbol})


@router.get("/stock-prices/{market}")
async def get_stock_prices(market: str = Path(..., pattern="^(kr|us)$")):
    slots = _get_slots(market)
    if not slots:
        return []
    slot_tuples = tuple((s["ticker"], s["name"], s["tv_symbol"]) for s in slots)
    results = await fetch_stock_prices(slot_tuples)
    return results
