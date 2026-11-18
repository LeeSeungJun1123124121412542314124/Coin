"""바이낸스 현물 수집기 테스트 — httpx.MockTransport로 네트워크 차단."""

from __future__ import annotations

import httpx
import pytest

from dashboard.backend.collectors import binance_spot
from dashboard.backend.collectors.binance_spot import (
    INTERVAL_MS,
    fetch_klines,
    fetch_spot_price,
    fetch_symbol_info,
    last_open_time,
    save_candles,
)

H4 = INTERVAL_MS["4h"]
TOTAL = 2500
NOW = TOTAL * H4 - 1  # 마지막(2499번째) 봉의 close_time == NOW-... → 미마감 처리


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _use_transport(monkeypatch, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(binance_spot, "_http_client", client)


@pytest.mark.asyncio
async def test_klines_paginate_and_drop_open_bar(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["startTime"])
        calls.append(start)
        first = start // H4
        rows = [
            [i * H4, "1", "2", "0.5", "1.5", "10", i * H4 + H4 - 1]
            for i in range(first, min(first + 1000, TOTAL))
        ]
        return httpx.Response(200, json=rows)

    _use_transport(monkeypatch, handler)
    bars = await fetch_klines("BTCUSDT", "4h", start_ms=0, now_ms=NOW)
    assert len(bars) == 2499 and len(calls) == 3
    assert all(b["open_time"] + INTERVAL_MS["4h"] <= NOW for b in bars)
    assert isinstance(bars[0]["close"], float)


@pytest.mark.asyncio
async def test_symbol_info_rejects_non_usdt_and_unknown(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        sym = request.url.params["symbol"]
        if sym == "NOPEUSDT":
            return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
        quote = "BTC" if sym == "ETHBTC" else "USDT"
        return httpx.Response(200, json={"symbols": [{
            "symbol": sym, "status": "TRADING",
            "baseAsset": sym.removesuffix(quote), "quoteAsset": quote,
        }]})

    _use_transport(monkeypatch, handler)
    assert await fetch_symbol_info("ETHBTC") is None
    assert await fetch_symbol_info("NOPEUSDT") is None
    assert (await fetch_symbol_info("SOLUSDT"))["base_asset"] == "SOL"


@pytest.mark.asyncio
async def test_spot_price(monkeypatch):
    _use_transport(monkeypatch, lambda r: httpx.Response(200, json={"symbol": "BTCUSDT", "price": "123.5"}))
    assert await fetch_spot_price("BTCUSDT") == 123.5


BARS = [
    {"open_time": i * 86_400_000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}
    for i in range(5)
]


def _count(conn_mod):
    return conn_mod.get_connection().execute("SELECT COUNT(*) FROM learning_candles").fetchone()[0]


def test_save_candles_idempotent(state_db):
    assert last_open_time("BTCUSDT", "1d") is None
    assert save_candles("BTCUSDT", "1d", BARS) == len(BARS)
    save_candles("BTCUSDT", "1d", BARS)
    assert _count(state_db) == len(BARS)
    assert last_open_time("BTCUSDT", "1d") == BARS[-1]["open_time"]
