"""학습 탭 추적 종목·설정 관리 + 상장일 백필 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
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
    client.post("/api/learning/symbols", json={"symbol": "ETHUSDT"})
    assert client.delete("/api/learning/symbols/ethusdt").status_code == 200
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
    add_symbol("ETHUSDT")
    with state_db_conn() as conn:
        conn.execute(
            "INSERT INTO learning_positions(symbol, status) VALUES ('ETHUSDT','open')")
    with pytest.raises(LearningError):
        remove_symbol("ETHUSDT")
    with state_db_conn() as conn:
        conn.execute("UPDATE learning_positions SET status='closed'")
    remove_symbol("ETHUSDT")
    assert list_symbols() == []


def _closed_position(symbol: str, opened: datetime) -> None:
    with state_db_conn() as conn:
        conn.execute(
            "INSERT INTO learning_positions(symbol, opened_at, status, closed_at) VALUES (?,?,'closed',?)",
            (symbol, opened.isoformat(), opened.isoformat()))


def test_remove_blocked_until_28d_review_close_collected(state_db):
    # 28일 복기 기준일 종가는 첫 진입 UTC 날짜 + 29일에 수집 — 그날까지는 청산된 포지션이라도 해제 거부 (R17)
    today = datetime.now(timezone.utc).date()
    add_symbol("ETHUSDT")
    noon = datetime(today.year, today.month, today.day, 12, tzinfo=timezone.utc)
    _closed_position("ETHUSDT", noon - timedelta(days=40))
    _closed_position("ETHUSDT", noon - timedelta(days=29))
    with pytest.raises(LearningError) as e:
        remove_symbol("ETHUSDT")
    assert (today + timedelta(days=1)).isoformat() in str(e.value)
    with state_db_conn() as conn:
        conn.execute("UPDATE learning_positions SET opened_at=?", ((noon - timedelta(days=30)).isoformat(),))
    remove_symbol("ETHUSDT")
    assert list_symbols() == []


def test_remove_uses_utc_date_of_first_entry(state_db):
    # 현지 20:00 -05:00 은 UTC로 다음 날 01:00 — 해제 가능일은 UTC 날짜 + 30일
    today = datetime.now(timezone.utc).date()
    add_symbol("ETHUSDT")
    local = (today - timedelta(days=29)).isoformat() + "T20:00:00-05:00"
    with state_db_conn() as conn:
        conn.execute("INSERT INTO learning_positions(symbol, opened_at, status) VALUES ('ETHUSDT', ?, 'closed')",
                     (local,))
    with pytest.raises(LearningError) as e:
        remove_symbol("ETHUSDT")
    assert (today + timedelta(days=2)).isoformat() in str(e.value)


def test_remove_dca_symbol_rejected(state_db):
    add_symbol("BTCUSDT")  # 기본 dca.symbol
    with pytest.raises(LearningError) as e:
        remove_symbol("BTCUSDT")
    assert "성과 탭에서 DCA 기준 종목을 바꾼 뒤 해제하세요" in str(e.value)
    add_symbol("ETHUSDT")
    update_settings({"dca": {"symbol": "ETHUSDT"}})
    remove_symbol("BTCUSDT")
    with pytest.raises(LearningError):
        remove_symbol("ETHUSDT")
    assert [s["symbol"] for s in list_symbols()] == ["ETHUSDT"]


def test_delete_dca_symbol_returns_400(client):
    client.post("/api/learning/symbols", json={"symbol": "BTCUSDT"})
    r = client.delete("/api/learning/symbols/BTCUSDT")
    assert r.status_code == 400 and "DCA" in r.json()["detail"]
    assert [s["symbol"] for s in client.get("/api/learning/symbols").json()] == ["BTCUSDT"]


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


@pytest.mark.parametrize("patch", [
    {"elliott": {"levels": [0.5, float("inf")]}},
    {"elliott": {"levels": [0.5, float("nan")]}},
    {"wyckoff": {"width_pct": float("inf")}},
    {"wyckoff": {"vol_mult": float("nan")}},
    {"elliott": {"threshold_1d": float("-inf")}},
])
def test_settings_reject_non_finite(state_db, patch):
    with pytest.raises(LearningError):
        update_settings(patch)
    assert get_settings()["elliott"]["levels"] == [0.382, 0.5, 0.618, 1.0, 1.618]


def test_settings_endpoint_rejects_infinity_literal(client):
    r = client.put("/api/learning/settings", content='{"elliott": {"levels": [0.5, Infinity]}}',
                   headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert client.get("/api/learning/settings").status_code == 200


def _binance_error(kind: str) -> Exception:
    req = httpx.Request("GET", "https://api.binance.com/api/v3/exchangeInfo")
    if kind == "network":
        return httpx.ConnectError("연결 실패", request=req)
    return httpx.HTTPStatusError("x", request=req, response=httpx.Response(int(kind), request=req))


@pytest.mark.parametrize("kind", ["451", "429", "502", "network"])
def test_add_symbol_binance_error_503(client, monkeypatch, kind):
    async def boom(symbol):
        raise _binance_error(kind)

    monkeypatch.setattr(binance_spot, "fetch_symbol_info", boom)
    r = client.post("/api/learning/symbols", json={"symbol": "BTCUSDT"})
    assert r.status_code == 503
    assert r.json() == {"detail": "바이낸스 조회에 실패했습니다. 잠시 후 다시 시도하세요"}
    assert client.get("/api/learning/symbols").json() == []
