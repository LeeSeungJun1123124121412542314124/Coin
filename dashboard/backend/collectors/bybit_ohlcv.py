"""바이비트 1시간봉 OHLCV 수집기 — 시뮬레이터 판정용."""

from __future__ import annotations

import logging

import httpx

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)

_BASE = "https://api.bybit.com"

# 모듈 레벨 httpx 클라이언트 — TCP/TLS 연결 재사용
_http_client: httpx.AsyncClient | None = None

_DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


async def fetch_bybit_ohlcv_1h(symbol: str, limit: int = 200) -> list[dict] | None:
    """바이비트 V5 API에서 1시간봉 OHLCV 조회.

    Args:
        symbol: 거래 심볼 (예: "BTCUSDT")
        limit: 조회할 봉 수 (최대 200)

    Returns:
        봉 데이터 리스트. 실패 시 None.
        각 항목: {"timestamp": int(ms), "open": float, "high": float,
                  "low": float, "close": float, "volume": float}
    """
    try:
        client = _get_client()
        resp = await client.get(
            f"{_BASE}/v5/market/kline",
            params={
                "category": "linear",
                "symbol": symbol,
                "interval": "60",
                "limit": limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("retCode") != 0:
            logger.error(
                "바이비트 kline API 오류 (%s): retCode=%s, msg=%s",
                symbol,
                data.get("retCode"),
                data.get("retMsg"),
            )
            return None

        rows = data.get("result", {}).get("list", [])
        if not rows:
            logger.warning("바이비트 kline 응답 비어있음 (%s)", symbol)
            return None

        # 응답은 최신순(내림차순) — 변환만 하고 순서는 유지
        bars = [
            {
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in rows
        ]
        return bars

    except httpx.HTTPStatusError as e:
        logger.error("HTTP 오류 (%s): %s", symbol, e)
        return None
    except httpx.RequestError as e:
        logger.error("네트워크 오류 (%s): %s", symbol, e)
        return None
    except (ValueError, KeyError, IndexError) as e:
        logger.error("응답 파싱 오류 (%s): %s", symbol, e, exc_info=True)
        return None


def save_ohlcv_1h(symbol: str, bars: list[dict]) -> int:
    """1시간봉 데이터를 coin_ohlcv_1h 테이블에 저장.

    Args:
        symbol: 거래 심볼
        bars: fetch_bybit_ohlcv_1h 반환값

    Returns:
        저장된 행 수
    """
    if not bars:
        return 0

    rows = [
        (
            symbol,
            bar["timestamp"],
            bar["open"],
            bar["high"],
            bar["low"],
            bar["close"],
            bar["volume"],
        )
        for bar in bars
    ]

    with get_db() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO coin_ohlcv_1h
               (symbol, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

    return len(rows)


async def collect_coin_ohlcv_1h(symbols: list[str] | None = None) -> None:
    """지정 심볼의 1시간봉 OHLCV를 수집하고 DB에 저장.

    Args:
        symbols: 수집할 심볼 목록. None이면 기본 목록 사용.
    """
    if symbols is None:
        symbols = _DEFAULT_SYMBOLS

    success_count = 0
    fail_count = 0

    for symbol in symbols:
        bars = await fetch_bybit_ohlcv_1h(symbol)
        if bars is None:
            logger.error("1시간봉 수집 실패: %s", symbol)
            fail_count += 1
            continue

        try:
            saved = save_ohlcv_1h(symbol, bars)
            logger.info("1시간봉 저장 완료: %s — %d개", symbol, saved)
            success_count += 1
        except Exception as e:
            logger.error("1시간봉 DB 저장 실패 (%s): %s", symbol, e)
            fail_count += 1

    logger.info(
        "1시간봉 수집 완료 — 성공: %d, 실패: %d",
        success_count,
        fail_count,
    )
