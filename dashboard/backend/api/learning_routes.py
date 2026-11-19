"""학습 탭 API 라우터 — 추적 종목·설정 관리."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend.collectors import binance_spot, exchange_rate
from dashboard.backend.db.connection import get_db
from dashboard.backend.services import (
    learning_account, learning_indicators, learning_metrics, learning_review, learning_symbols,
)
from dashboard.backend.services.learning_snapshot import build_snapshot
from dashboard.backend.services.learning_settings import LearningError, get_settings, update_settings

router = APIRouter()

# Binance kline 간격 (대소문자 구분: 1m이 아니라 1M이 월봉)
Interval = Literal["1h", "4h", "1d", "1w", "1M"]


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
    try:
        info = await binance_spot.fetch_symbol_info(symbol)
    except httpx.HTTPError:  # 451·429·5xx·네트워크 오류 — 없는 종목(400)과 구분
        return JSONResponse(status_code=503, content={"detail": "바이낸스 조회에 실패했습니다. 잠시 후 다시 시도하세요"})
    if info is None:
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


def _is_tracked(symbol: str) -> bool:
    return symbol in {s["symbol"] for s in learning_symbols.list_symbols()}


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


def _chart_indicators(candles: list[dict], cfg: dict, t0: int) -> dict:
    """켜진 보조 지표만 전체 봉으로 계산한 뒤 보이는 봉(t0 이후)의 정의된 점만 남긴다."""
    times = [c["open_time"] for c in candles]
    closes = [c["close"] for c in candles]

    def pick(series: list, make) -> list:
        return [make(t, v) for t, v in zip(times, series) if v is not None and t >= t0]

    out: dict = {}
    if cfg["ma"]["enabled"]:
        fn = learning_indicators.ema if cfg["ma"]["type"] == "ema" else learning_indicators.sma
        out["ma"] = [
            {"period": p, "points": pick(fn(closes, p), lambda t, v: {"time": t, "value": v})}
            for p in cfg["ma"]["periods"]
        ]
    if cfg["bb"]["enabled"]:
        bb = learning_indicators.bollinger(closes, cfg["bb"]["period"], cfg["bb"]["stddev"])
        out["bb"] = pick(bb, lambda t, v: {"time": t, **v})
    if cfg["rsi"]["enabled"]:
        out["rsi"] = pick(learning_indicators.rsi(closes, cfg["rsi"]["period"]),
                          lambda t, v: {"time": t, "value": v})
    if cfg["macd"]["enabled"]:
        m = cfg["macd"]
        out["macd"] = pick(learning_indicators.macd(closes, m["fast"], m["slow"], m["signal"]),
                           lambda t, v: {"time": t, **v})
    return out


@router.get("/learning/chart")
async def get_chart(
    symbol: str,
    interval: Interval = "1d",
    limit: int = Query(500, ge=1, le=2000),
):
    """차트용 캔들·일목·와이코프·지그재그·피보나치. 지표는 limit + 워밍업(최소 52, 켜진 보조 지표에 따라 최대 1500)봉으로 계산 후 잘라 반환."""
    symbol = symbol.strip().upper()
    if not _is_tracked(symbol):
        return _not_tracked(symbol)
    settings = get_settings()
    ind_cfg = settings["indicators"]
    candles = _load_candles(
        symbol, interval, limit + max(_EXTRA_BARS, learning_indicators.indicator_warmup(ind_cfg)))
    if not candles:
        return {"candles": [], "ichimoku": [], "indicators": {},
                "wyckoff": {"volume_spikes": [], "candidates": [], "current_box": None},
                "pivots": [], "fib": [], "state": dict(_STATE_NONE), "settings": settings}
    wy, el = settings["wyckoff"], settings["elliott"]
    ich = learning_indicators.ichimoku(candles, interval)
    state = learning_indicators.ichimoku_state(candles, ich)
    wyckoff = learning_indicators.wyckoff_candidates(candles, wy["n"], wy["width_pct"], wy["vol_mult"])
    pivots = learning_indicators.zigzag(candles, el[f"threshold_{interval}"])
    fib = learning_indicators.fib_levels(pivots, el["levels"])

    shown = candles[-limit:]
    t0 = shown[0]["open_time"]
    return {
        "candles": shown,
        "indicators": _chart_indicators(candles, ind_cfg, t0),
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
    ich = learning_indicators.ichimoku(candles, interval)
    wyckoff = learning_indicators.wyckoff_candidates(candles, wy["n"], wy["width_pct"], wy["vol_mult"])
    since = candles[-5:][0]["open_time"]
    return {
        "ichimoku_state": learning_indicators.ichimoku_state(candles, ich),
        "wyckoff_recent": [c for c in wyckoff["candidates"] if c["time"] >= since],
        "current_box": wyckoff["current_box"],
    }


@router.get("/learning/order-context")
async def get_order_context(symbol: str, interval: Interval = "1d"):
    """주문 근거 미리 채우기용 — 일목 상태, 최근 5봉 안의 와이코프 후보, 현재 박스."""
    symbol = symbol.strip().upper()
    if not _is_tracked(symbol):
        return _not_tracked(symbol)
    return _order_context(symbol, interval)


class OrderRequest(BaseModel):
    """모의 주문 요청 — 매수는 usdt_amount, 매도는 qty만 허용."""
    symbol: str = Field(..., min_length=1)
    side: str
    usdt_amount: float | None = None
    qty: float | None = None
    rationale: dict
    interval: Interval = "1d"


@router.get("/learning/account")
async def get_learning_account():
    symbols = [p["symbol"] for p in learning_account.open_positions()]
    prices = {}
    for sym in symbols:
        price = await binance_spot.fetch_spot_price(sym)
        if price is not None:
            prices[sym] = price
    usd_krw = await exchange_rate.fetch_usd_krw()
    return {**learning_account.get_account(), **learning_account.holdings(prices, usd_krw), "usd_krw": usd_krw}


@router.post("/learning/orders", status_code=201)
async def post_order(req: OrderRequest):
    symbol = req.symbol.strip().upper()
    if not _is_tracked(symbol):
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
            usdt_amount=req.usdt_amount, qty=req.qty, detected={**_order_context(symbol, req.interval), "interval": req.interval})
    except LearningError as e:
        return _bad_request(e)


@router.get("/learning/journal")
async def get_learning_journal(limit: int = Query(50, ge=1, le=200)):
    return learning_review.journal(limit)


def _no_position(position_id: int) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"포지션을 찾을 수 없습니다: {position_id}"})


@router.get("/learning/reviews/{position_id}")
async def get_learning_reviews(position_id: int):
    if not learning_review.position_exists(position_id):
        return _no_position(position_id)
    return {str(h): learning_review.review_position(position_id, h) for h in learning_review.HORIZONS}


class ReviewConfirmRequest(BaseModel):
    """복기 판정 확정 요청 바디."""
    verdict: str
    reason: str


@router.post("/learning/reviews/{position_id}/{horizon_days}/confirm")
async def post_review_confirm(position_id: int, horizon_days: int, req: ReviewConfirmRequest):
    if not learning_review.position_exists(position_id):
        return _no_position(position_id)
    try:
        return learning_review.confirm_review(position_id, horizon_days, req.verdict, req.reason)
    except LearningError as e:
        return _bad_request(e)


@router.get("/learning/performance")
async def get_learning_performance():
    """적중률·승률·계좌 자산 곡선·DCA 기준선·환율."""
    start = datetime.fromisoformat(learning_account.get_account()["started_at"]).astimezone(timezone.utc).date()
    until = datetime.now(timezone.utc).date()
    symbol = get_settings()["dca"]["symbol"]
    with get_db() as conn:
        rows = conn.execute(
            "SELECT open_time, close FROM learning_candles WHERE symbol=? AND interval='1d' ORDER BY open_time",
            (symbol,)).fetchall()
    if rows:
        closes = {datetime.fromtimestamp(r["open_time"] / 1000, tz=timezone.utc).date(): r["close"] for r in rows}
        dca = {"symbol": symbol, "series": learning_metrics.dca_baseline(start, until, closes)}
        dca_reason = None
    else:
        dca = None
        dca_reason = f"기준 종목({symbol}) 캔들이 없습니다. 추적 목록에 추가하세요"
    return {
        "hit_rate": {"14": learning_metrics.hit_rate(14), "28": learning_metrics.hit_rate(28)},
        "win_rate": learning_metrics.win_rate(),
        "equity": learning_metrics.account_equity_series(start, until),
        "dca": dca,
        "dca_reason": dca_reason,
        "usd_krw": await exchange_rate.fetch_usd_krw(),
    }
