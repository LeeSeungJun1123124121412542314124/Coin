"""바이낸스 현물 캔들·시세 수집기 — 학습 탭용."""

from __future__ import annotations

import logging
import time

import httpx

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)

BASE = "https://api.binance.com"
_PAGE_LIMIT = 1000

# 모듈 레벨 httpx 클라이언트 — TCP/TLS 연결 재사용
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


async def fetch_symbol_info(symbol: str) -> dict | None:
    """USDT 현물 거래 가능 심볼이면 {"symbol","base_asset"}, 아니면 None (400 포함)."""
    resp = await _get_client().get(f"{BASE}/api/v3/exchangeInfo", params={"symbol": symbol})
    if resp.status_code == 400:
        return None
    resp.raise_for_status()
    for info in resp.json().get("symbols", []):
        if (
            info.get("symbol") == symbol
            and info.get("status") == "TRADING"
            and info.get("quoteAsset") == "USDT"
        ):
            return {"symbol": symbol, "base_asset": info["baseAsset"]}
    return None


async def fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int | None = None,
    now_ms: int | None = None,
) -> list[dict]:
    """start_ms부터 마감된 봉만 1000개씩 페이지네이션으로 수집 (open_time 오름차순)."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    bars: list[dict] = []
    cursor = start_ms
    while True:
        params = {"symbol": symbol, "interval": interval, "startTime": cursor, "limit": _PAGE_LIMIT}
        if end_ms is not None:
            params["endTime"] = end_ms
        resp = await _get_client().get(f"{BASE}/api/v3/klines", params=params)
        resp.raise_for_status()
        rows = resp.json()

        for row in rows:
            if int(row[6]) >= now_ms:  # closeTime 기준 — 아직 마감 전인 봉 제외 (월봉 등 가변 길이 대응)
                continue
            bars.append({
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })

        if len(rows) < _PAGE_LIMIT:
            break
        cursor = int(rows[-1][6]) + 1  # 마지막 행 closeTime 다음 ms부터
    return bars


async def fetch_spot_price(symbol: str) -> float | None:
    """현물 현재가 조회. 실패 시 None."""
    try:
        resp = await _get_client().get(f"{BASE}/api/v3/ticker/price", params={"symbol": symbol})
        resp.raise_for_status()
        return float(resp.json()["price"])
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.error("바이낸스 현물 시세 조회 실패 (%s): %s", symbol, e)
        return None


def save_candles(symbol: str, interval: str, bars: list[dict]) -> int:
    """캔들을 learning_candles에 upsert. 처리한 행 수 반환."""
    if not bars:
        return 0
    rows = [
        (symbol, interval, b["open_time"], b["open"], b["high"], b["low"], b["close"], b["volume"])
        for b in bars
    ]
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO learning_candles
               (symbol, interval, open_time, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            rows,
        )
    return len(rows)


def last_open_time(symbol: str, interval: str) -> int | None:
    """저장된 마지막 봉의 open_time. 없으면 None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT MAX(open_time) FROM learning_candles WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()
    return row[0] if row and row[0] is not None else None
