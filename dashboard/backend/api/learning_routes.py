"""학습 탭 API 라우터 — 추적 종목·설정 관리."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend.collectors import binance_spot
from dashboard.backend.services import learning_symbols
from dashboard.backend.services.learning_settings import LearningError, get_settings, update_settings

router = APIRouter()


class SymbolAddRequest(BaseModel):
    """추적 종목 추가 요청 바디."""
    symbol: str = Field(..., min_length=1)


def _bad_request(e: LearningError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(e)})


@router.get("/learning/symbols")
async def get_symbols():
    return learning_symbols.list_symbols()


@router.post("/learning/symbols", status_code=202)
async def post_symbol(request: SymbolAddRequest, background_tasks: BackgroundTasks):
    """바이낸스 USDT 현물 존재 확인 → 추가 → 백그라운드 백필."""
    symbol = request.symbol.strip().upper()
    if await binance_spot.fetch_symbol_info(symbol) is None:
        return _bad_request(LearningError(f"바이낸스 USDT 현물에 없는 종목입니다: {symbol}"))
    try:
        added = learning_symbols.add_symbol(symbol)
    except LearningError as e:
        return _bad_request(e)
    background_tasks.add_task(learning_symbols.backfill_symbol, symbol)
    return JSONResponse(status_code=202, content=added, background=background_tasks)


@router.delete("/learning/symbols/{symbol}")
async def delete_symbol(symbol: str):
    try:
        learning_symbols.remove_symbol(symbol)
    except LearningError as e:
        return _bad_request(e)
    return {"removed": symbol.upper()}


@router.get("/learning/settings")
async def get_learning_settings():
    return get_settings()


@router.put("/learning/settings")
async def put_learning_settings(patch: dict):
    try:
        return update_settings(patch)
    except LearningError as e:
        return _bad_request(e)
