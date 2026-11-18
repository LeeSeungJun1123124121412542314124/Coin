"""학습 주문 근거 필수 검증·주문 API 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ICH = {"cloud_position": "above", "tk_cross": "golden", "chikou": "above", "future_cloud": "bullish"}
GOOD = {"phase": "markup", "ichimoku": _ICH}


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
def client(state_db, monkeypatch):
    from dashboard.backend.api.learning_routes import router
    from dashboard.backend.collectors import binance_spot, exchange_rate
    from dashboard.backend.db.connection import get_db

    async def price(symbol):
        return 50000.0

    async def rate():
        return 1400.0

    monkeypatch.setattr(binance_spot, "fetch_spot_price", price)
    monkeypatch.setattr(exchange_rate, "fetch_usd_krw", rate)
    with get_db() as conn:
        conn.execute("INSERT INTO learning_symbols(symbol) VALUES ('BTCUSDT')")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _buy(client, rationale, **kw):
    body = {"symbol": "BTCUSDT", "side": "buy", "usdt_amount": 1000.0, "rationale": rationale}
    body.update(kw)
    return client.post("/api/learning/orders", json=body)


def _sell(client, rationale, **kw):
    body = {"symbol": "BTCUSDT", "side": "sell", "qty": 0.01, "rationale": rationale}
    body.update(kw)
    return client.post("/api/learning/orders", json=body)


@pytest.mark.parametrize("bad", [{}, {"phase": "moon"}, {"phase": "markup"},
                                 {"phase": "markup", "ichimoku": {"cloud_position": "above"}}])
def test_rationale_required_for_buy_and_sell(bad, client):
    assert _buy(client, GOOD).status_code == 201  # 매도 검증용 보유 확보
    assert _buy(client, bad).status_code == 400
    assert _sell(client, bad).status_code == 400


def test_validate_rationale_rules(state_db):
    from dashboard.backend.services.learning_account import validate_rationale
    from dashboard.backend.services.learning_settings import LearningError
    undecided = {"phase": "unclear", "ichimoku": {k: None for k in _ICH}}
    assert validate_rationale(undecided)["ichimoku"] == undecided["ichimoku"]
    for bad in (
        {"phase": "markup", "ichimoku": {**_ICH, "tk_cross": "x"}},
        {"phase": "markup", "ichimoku": _ICH, "memo": 5},
        {"phase": "markup", "ichimoku": _ICH, "memo": "a" * 2001},
        {"phase": None, "ichimoku": _ICH},
    ):
        with pytest.raises(LearningError):
            validate_rationale(bad)
    assert validate_rationale({**GOOD, "memo": "a" * 2000})["memo"] == "a" * 2000


def test_memo_optional(client):
    assert _buy(client, GOOD).status_code == 201


def test_wrong_field_for_side_400(client):
    assert _buy(client, GOOD, qty=1.0).status_code == 400
    assert _buy(client, GOOD).status_code == 201
    assert _sell(client, GOOD, usdt_amount=10.0).status_code == 400
    assert _buy(client, GOOD, side="hold").status_code == 400


def test_untracked_symbol_400(client):
    assert _buy(client, GOOD, symbol="ETHUSDT").status_code == 400


def test_price_failure_503(client, monkeypatch):
    from dashboard.backend.collectors import binance_spot

    async def none(symbol):
        return None

    monkeypatch.setattr(binance_spot, "fetch_spot_price", none)
    r = _buy(client, GOOD)
    assert r.status_code == 503 and r.json()["detail"]


def test_order_context_prefill(client):
    from dashboard.backend.db.connection import get_db
    ctx = client.get("/api/learning/order-context", params={"symbol": "BTCUSDT"}).json()
    assert set(ctx) == {"ichimoku_state", "wyckoff_recent", "current_box"}
    assert _buy(client, GOOD).status_code == 201
    with get_db() as conn:
        row = conn.execute("SELECT detected_json, phase, ichimoku_json FROM learning_fills").fetchone()
    assert json.loads(row["detected_json"]) == ctx
    assert row["phase"] == "markup" and json.loads(row["ichimoku_json"]) == _ICH


def test_order_succeeds_with_empty_snapshot(client):
    from dashboard.backend.db.connection import get_db
    assert _buy(client, GOOD).status_code == 201
    with get_db() as conn:
        snap = json.loads(conn.execute("SELECT snapshot_json FROM learning_fills").fetchone()[0])
    assert snap["items"]["mvrv"]["value"] is None and snap["items"]["mvrv"]["reason"]


def test_account_endpoint(client):
    assert _buy(client, GOOD).status_code == 201
    a = client.get("/api/learning/account").json()
    assert a["cash_usdt"] == pytest.approx(9000.0)
    assert a["positions"][0]["symbol"] == "BTCUSDT"
    assert a["equity_usdt"] == pytest.approx(9000.0 + 999.0)
    assert a["equity_krw"] == pytest.approx(a["equity_usdt"] * 1400.0)
