"""코인 슬롯 관리 API 라우터 — 6개 슬롯 조회 및 교체."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend import cache
from dashboard.backend.collectors.coingecko import search_coin, verify_price
from dashboard.backend.db.coin_slots import get_slots, update_slot
from dashboard.backend.utils.errors import api_error

logger = logging.getLogger(__name__)
router = APIRouter()


class SlotUpdateRequest(BaseModel):
    """슬롯 교체 요청 바디."""
    query: str = Field(..., min_length=1)


@router.get("/coin-slots")
async def get_coin_slots():
    """현재 6개 슬롯 반환."""
    return get_slots()


@router.put("/coin-slots/{position}")
async def put_coin_slot(
    request: SlotUpdateRequest,
    position: int = Path(..., ge=0, le=5),
):
    """슬롯 교체.

    1. 코인 검색 → 없으면 404
    2. 가격 유효성 확인 → 없으면 422
    3. TradingView 심볼 자동 추론
    4. 슬롯 업데이트
    5. 가격 캐시 무효화
    """
    # 1. 코인 검색
    coin = await search_coin(request.query)
    if coin is None:
        return api_error(404, "SYMBOL_NOT_FOUND", f"'{request.query}'에 해당하는 코인을 찾을 수 없습니다.")

    coin_id: str = coin["id"]
    symbol: str = coin["symbol"]

    # 2. 가격 유효성 확인
    price_info = await verify_price(coin_id)
    if price_info is None:
        return api_error(422, "PRICE_UNAVAILABLE", f"'{symbol}' 코인의 가격 정보를 가져올 수 없습니다.")

    # 3. TradingView 심볼 자동 추론
    tv_symbol = f"BINANCE:{symbol.upper()}USDT"

    # 4. 슬롯 업데이트
    try:
        update_slot(position, coin_id, symbol, tv_symbol)
    except ValueError:
        return api_error(400, "INVALID_POSITION", f"유효하지 않은 슬롯 위치: {position}")

    # 5. 가격 캐시 무효화
    cache.delete_prefix("coingecko_prices")

    return JSONResponse({
        "position": position,
        "coin_id": coin_id,
        "symbol": symbol,
        "tv_symbol": tv_symbol,
        "preview": {
            "price": price_info["price"],
            "change_24h": price_info["change_24h"],
        },
    })
