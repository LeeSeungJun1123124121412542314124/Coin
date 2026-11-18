"""학습 탭 추적 종목 관리 + 상장일 백필."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from dashboard.backend.collectors import binance_spot
from dashboard.backend.db.connection import get_db
from dashboard.backend.services.learning_settings import LearningError

logger = logging.getLogger(__name__)

MAX_SYMBOLS = 5


def list_symbols() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT symbol, listed_at, added_at, backfill_status "
            "FROM learning_symbols ORDER BY added_at, symbol"
        ).fetchall()
    return [
        {"symbol": r[0], "listed_at": r[1], "added_at": r[2], "backfill_status": r[3]}
        for r in rows
    ]


def add_symbol(symbol: str) -> dict:
    """종목을 pending 상태로 추가. 중복·6번째는 LearningError."""
    symbol = symbol.strip().upper()
    if not symbol:
        raise LearningError("종목 심볼이 비어 있습니다.")
    current = list_symbols()
    if any(s["symbol"] == symbol for s in current):
        raise LearningError(f"이미 추적 중인 종목입니다: {symbol}")
    if len(current) >= MAX_SYMBOLS:
        raise LearningError(f"추적 종목은 최대 {MAX_SYMBOLS}개까지 가능합니다.")
    added_at = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO learning_symbols(symbol, added_at, backfill_status) VALUES (?, ?, 'pending')",
            (symbol, added_at),
        )
    return {"symbol": symbol, "listed_at": None, "added_at": added_at, "backfill_status": "pending"}


def remove_symbol(symbol: str) -> None:
    """종목 제거. 열린 포지션이 있으면 LearningError."""
    symbol = symbol.strip().upper()
    with get_db() as conn:
        open_cnt = conn.execute(
            "SELECT COUNT(*) FROM learning_positions WHERE symbol=? AND status='open'", (symbol,)
        ).fetchone()[0]
        if open_cnt:
            raise LearningError(f"열린 포지션이 있는 종목은 제거할 수 없습니다: {symbol}")
        conn.execute("DELETE FROM learning_symbols WHERE symbol=?", (symbol,))


def _set_status(symbol: str, status: str, listed_at: str | None = None) -> None:
    with get_db() as conn:
        if listed_at is not None:
            conn.execute(
                "UPDATE learning_symbols SET backfill_status=?, listed_at=? WHERE symbol=?",
                (status, listed_at, symbol),
            )
        else:
            conn.execute(
                "UPDATE learning_symbols SET backfill_status=? WHERE symbol=?", (status, symbol)
            )


async def backfill_symbol(symbol: str) -> dict:
    """1d·4h 전체 이력을 상장일부터 수집·저장. 실패해도 예외를 던지지 않고 failed 처리."""
    symbol = symbol.strip().upper()
    try:
        daily = await binance_spot.fetch_klines(symbol, "1d", 0)
        if not daily:
            raise RuntimeError("1d 캔들이 비어 있습니다.")
        h4 = await binance_spot.fetch_klines(symbol, "4h", 0)
        binance_spot.save_candles(symbol, "1d", daily)
        binance_spot.save_candles(symbol, "4h", h4)
        listed_at = datetime.fromtimestamp(daily[0]["open_time"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        _set_status(symbol, "done", listed_at)
        return {"symbol": symbol, "status": "done", "listed_at": listed_at}
    except Exception as e:
        logger.error("학습 종목 백필 실패 (%s): %s", symbol, e, exc_info=True)
        _set_status(symbol, "failed")
        return {"symbol": symbol, "status": "failed", "error": str(e)}
