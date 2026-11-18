"""학습 탭 추적 종목·설정 관리 + 상장일 백필 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.collectors import binance_spot
from dashboard.backend.services.learning_settings import (
    LearningError,
    get_settings,
    update_settings,
)
from dashboard.backend.services.learning_symbols import (
    add_symbol,
    backfill_symbol,
    list_symbols,
    remove_symbol,
)

_DAY = 86_400_000
_H4 = 14_400_000
_START = int(datetime(2017, 8, 17, tzinfo=timezone.utc).timestamp() * 1000)


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


@pytest.fixture
def mock_binance(monkeypatch):
    """모든 *USDT 존재 + 1d 3000봉 / 4h 18000봉 (2017-08-17 시작)."""
    async def info(symbol):
        if symbol.startswith("NOPE"):
            return None
        return {"symbol": symbol, "base_asset": symbol[:-4]}

    async def klines(symbol, interval, start_ms, end_ms=None, now_ms=None):
        step, n = (_DAY, 3000) if interval == "1d" else (_H4, 18000)
        return [
            {"open_time": _START + i * step, "open": 1.0, "high": 2.0,
             "low": 0.5, "close": 1.5, "volume": 10.0}
            for i in range(n)
        ]

    monkeypatch.setattr(binance_spot, "fetch_symbol_info", info)
    monkeypatch.setattr(binance_spot, "fetch_klines", klines)


@pytest.fixture
def client(state_db, mock_binance):
    from dashboard.backend.api.learning_routes import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _count(table, **where):
    with state_db_conn() as conn:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(f"{k}=?" for k in where)
        return conn.execute(sql, tuple(where.values())).fetchone()[0]


def state_db_conn():
    from dashboard.backend.db.connection import get_db
    return get_db()


def test_add_up_to_five_then_reject(client):
    for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]:
        assert client.post("/api/learning/symbols", json={"symbol": s}).status_code == 202
    r = client.post("/api/learning/symbols", json={"symbol": "ADAUSDT"})
    assert r.status_code == 400 and "5" in r.json()["detail"]


def test_unknown_pair_rejected(client):
    assert client.post("/api/learning/symbols", json={"symbol": "NOPEUSDT"}).status_code == 400


def test_duplicate_rejected_and_uppercase(client):
    assert client.post("/api/learning/symbols", json={"symbol": "btcusdt"}).status_code == 202
    assert [s["symbol"] for s in client.get("/api/learning/symbols").json()] == ["BTCUSDT"]
    assert client.post("/api/learning/symbols", json={"symbol": "BTCUSDT"}).status_code == 400


def test_post_runs_backfill_in_background(client):
    client.post("/api/learning/symbols", json={"symbol": "BTCUSDT"})
    sym = client.get("/api/learning/symbols").json()[0]
    assert sym["backfill_status"] == "done" and sym["listed_at"] == "2017-08-17"


def test_delete_symbol(client):
    client.post("/api/learning/symbols", json={"symbol": "BTCUSDT"})
    assert client.delete("/api/learning/symbols/btcusdt").status_code == 200
    assert client.get("/api/learning/symbols").json() == []


@pytest.mark.asyncio
async def test_backfill_from_listing(state_db, mock_binance):
    add_symbol("BTCUSDT")
    assert list_symbols()[0]["backfill_status"] == "pending"
    res = await backfill_symbol("BTCUSDT")
    assert res["status"] == "done" and list_symbols()[0]["listed_at"] == "2017-08-17"
    assert _count("learning_candles", interval="1d") == 3000
    assert _count("learning_candles", interval="4h") == 18000


@pytest.mark.asyncio
async def test_backfill_failure_sets_failed(state_db, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("네트워크 오류")
    monkeypatch.setattr(binance_spot, "fetch_klines", boom)
    add_symbol("BTCUSDT")
    res = await backfill_symbol("BTCUSDT")
    assert res["status"] == "failed" and list_symbols()[0]["backfill_status"] == "failed"


def test_remove_with_open_position_rejected(state_db):
    add_symbol("BTCUSDT")
    with state_db_conn() as conn:
        conn.execute(
            "INSERT INTO learning_positions(symbol, status) VALUES ('BTCUSDT','open')")
    with pytest.raises(LearningError):
        remove_symbol("BTCUSDT")
    with state_db_conn() as conn:
        conn.execute("UPDATE learning_positions SET status='closed'")
    remove_symbol("BTCUSDT")
    assert list_symbols() == []


def test_settings_defaults_and_merge(state_db):
    assert get_settings()["wyckoff"]["n"] == 30
    res = update_settings({"wyckoff": {"n": 50}})
    assert res["wyckoff"] == {"n": 50, "width_pct": 15.0, "vol_mult": 2.0}
    assert get_settings()["wyckoff"]["n"] == 50
    assert get_settings()["elliott"]["threshold_1d"] == 10.0


def test_settings_validation(state_db):
    with pytest.raises(LearningError):
        update_settings({"wyckoff": {"n": 2}})
    with pytest.raises(LearningError):
        update_settings({"dca": {"symbol": "ETHUSDT"}})  # 미추적
    with pytest.raises(LearningError):
        update_settings({"elliott": {"levels": []}})
    with pytest.raises(LearningError):
        update_settings({"elliott": {"levels": [0.5, -1]}})
    with pytest.raises(LearningError):
        update_settings({"elliott": {"threshold_4h": 99}})
    add_symbol("ETHUSDT")
    assert update_settings({"dca": {"symbol": "ETHUSDT"}})["dca"]["symbol"] == "ETHUSDT"


def test_settings_endpoints(client):
    assert client.get("/api/learning/settings").json()["wyckoff"]["n"] == 30
    r = client.put("/api/learning/settings", json={"wyckoff": {"n": 2}})
    assert r.status_code == 400 and "detail" in r.json()
    r = client.put("/api/learning/settings", json={"wyckoff": {"n": 40}})
    assert r.status_code == 200 and r.json()["wyckoff"]["n"] == 40
