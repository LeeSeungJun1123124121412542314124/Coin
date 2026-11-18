"""학습 탭 API 라우터 — 추적 종목·설정 관리."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend.collectors import binance_spot, exchange_rate
from dashboard.backend.db.connection import get_db
from dashboard.backend.services import learning_account, learning_indicators, learning_symbols
from dashboard.backend.services.learning_snapshot import build_snapshot
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


_EXTRA_BARS = 52  # 일목 선행스팬B(52봉) 계산용 추가 봉
_STATE_NONE = {"cloud_position": None, "tk_cross": None, "chikou": None, "future_cloud": None}


def _not_tracked(symbol: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"추적 중이지 않은 종목입니다: {symbol}"})


def _load_candles(symbol: str, interval: str, count: int) -> list[dict]:
    """최신 count봉을 시간 오름차순으로 읽는다."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT open_time, open, high, low, close, volume FROM learning_candles"
            " WHERE symbol=? AND interval=? ORDER BY open_time DESC LIMIT ?",
            (symbol, interval, count),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


@router.get("/learning/chart")
async def get_chart(
    symbol: str,
    interval: Literal["1d", "4h"] = "1d",
    limit: int = Query(500, ge=1, le=2000),
):
    """차트용 캔들·일목·와이코프·지그재그·피보나치. 지표는 limit+52봉으로 계산 후 잘라 반환."""
    symbol = symbol.strip().upper()
    if symbol not in {s["symbol"] for s in learning_symbols.list_symbols()}:
        return _not_tracked(symbol)
    settings = get_settings()
    candles = _load_candles(symbol, interval, limit + _EXTRA_BARS)
    if not candles:
        return {"candles": [], "ichimoku": [],
                "wyckoff": {"volume_spikes": [], "candidates": [], "current_box": None},
                "pivots": [], "fib": [], "state": dict(_STATE_NONE), "settings": settings}
    wy, el = settings["wyckoff"], settings["elliott"]
    ich = learning_indicators.ichimoku(candles, binance_spot.INTERVAL_MS[interval])
    state = learning_indicators.ichimoku_state(candles, ich)
    wyckoff = learning_indicators.wyckoff_candidates(candles, wy["n"], wy["width_pct"], wy["vol_mult"])
    pivots = learning_indicators.zigzag(candles, el["threshold_1d" if interval == "1d" else "threshold_4h"])
    fib = learning_indicators.fib_levels(pivots, el["levels"])

    shown = candles[-limit:]
    t0 = shown[0]["open_time"]
    return {
        "candles": shown,
        "ichimoku": [r for r in ich if r["time"] >= t0],
        "wyckoff": {
            "volume_spikes": [t for t in wyckoff["volume_spikes"] if t >= t0],
            "candidates": [c for c in wyckoff["candidates"] if c["time"] >= t0],
            "current_box": wyckoff["current_box"],
        },
        "pivots": [p for p in pivots if p["time"] >= t0],
        "fib": fib,
        "state": state,
        "settings": settings,
    }


def _order_context(symbol: str, interval: str) -> dict:
    """주문 근거 미리 채우기용 — 일목 상태, 최근 5봉 안의 와이코프 후보, 현재 박스."""
    candles = _load_candles(symbol, interval, 500 + _EXTRA_BARS)
    if not candles:
        return {"ichimoku_state": dict(_STATE_NONE), "wyckoff_recent": [], "current_box": None}
    wy = get_settings()["wyckoff"]
    ich = learning_indicators.ichimoku(candles, binance_spot.INTERVAL_MS[interval])
    wyckoff = learning_indicators.wyckoff_candidates(candles, wy["n"], wy["width_pct"], wy["vol_mult"])
    since = candles[-5:][0]["open_time"]
    return {
        "ichimoku_state": learning_indicators.ichimoku_state(candles, ich),
        "wyckoff_recent": [c for c in wyckoff["candidates"] if c["time"] >= since],
        "current_box": wyckoff["current_box"],
    }


@router.get("/learning/order-context")
async def get_order_context(symbol: str, interval: Literal["1d", "4h"] = "1d"):
    """주문 근거 미리 채우기용 — 일목 상태, 최근 5봉 안의 와이코프 후보, 현재 박스."""
    symbol = symbol.strip().upper()
    if symbol not in {s["symbol"] for s in learning_symbols.list_symbols()}:
        return _not_tracked(symbol)
    return _order_context(symbol, interval)


class OrderRequest(BaseModel):
    """모의 주문 요청 — 매수는 usdt_amount, 매도는 qty만 허용."""
    symbol: str = Field(..., min_length=1)
    side: str
    usdt_amount: float | None = None
    qty: float | None = None
    rationale: dict
    interval: Literal["1d", "4h"] = "1d"


@router.get("/learning/account")
async def get_learning_account():
    symbols = [p["symbol"] for p in learning_account.open_positions()]
    prices = {}
    for sym in symbols:
        price = await binance_spot.fetch_spot_price(sym)
        if price is not None:
            prices[sym] = price
    usd_krw = await exchange_rate.fetch_usd_krw()
    return {**learning_account.get_account(), **learning_account.holdings(prices, usd_krw)}


@router.post("/learning/orders", status_code=201)
async def post_order(req: OrderRequest):
    symbol = req.symbol.strip().upper()
    if symbol not in {s["symbol"] for s in learning_symbols.list_symbols()}:
        return _bad_request(LearningError("추적 중인 종목만 주문할 수 있습니다"))
    if req.side not in ("buy", "sell"):
        return _bad_request(LearningError(f"주문 방향이 올바르지 않습니다: {req.side}"))
    if req.side == "buy" and (req.qty is not None or req.usdt_amount is None):
        return _bad_request(LearningError("매수는 usdt_amount만 지정해야 합니다"))
    if req.side == "sell" and (req.usdt_amount is not None or req.qty is None):
        return _bad_request(LearningError("매도는 qty만 지정해야 합니다"))
    try:
        rationale = learning_account.validate_rationale(req.rationale)
    except LearningError as e:
        return _bad_request(e)
    price = await binance_spot.fetch_spot_price(symbol)
    if price is None:
        return JSONResponse(status_code=503, content={"detail": "현재가를 가져오지 못했습니다. 잠시 후 다시 시도하세요"})
    try:
        return learning_account.place_order(
            symbol, req.side, price, rationale, build_snapshot(symbol),
            usdt_amount=req.usdt_amount, qty=req.qty, detected=_order_context(symbol, req.interval))
    except LearningError as e:
        return _bad_request(e)
