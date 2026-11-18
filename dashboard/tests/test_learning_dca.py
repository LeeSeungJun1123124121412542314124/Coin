"""DCA 기준선·계좌 자산 곡선 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.services.learning_metrics import dca_baseline

_ICH = {"cloud_position": "above", "tk_cross": "golden", "chikou": "above", "future_cloud": "bullish"}
R = {"phase": "markup", "ichimoku": _ICH}


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
    from dashboard.backend.api import learning_routes
    from dashboard.backend.collectors import exchange_rate

    async def _krw():
        return 1400.0
    monkeypatch.setattr(exchange_rate, "fetch_usd_krw", _krw)
    app = FastAPI()
    app.include_router(learning_routes.router, prefix="/api")
    return TestClient(app)


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _candle(symbol, d: date, close):
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO learning_candles(symbol, interval, open_time, open, high, low, close, volume)"
            " VALUES (?, '1d', ?, ?, ?, ?, ?, 1)", (symbol, _ms(d), close, close, close, close))


def test_dca_52_weeks():
    start = date(2026, 1, 1)
    closes = {start + timedelta(d): 100.0 for d in range(400)}
    s = dca_baseline(start, start + timedelta(399), closes)
    assert s[0]["date"] == "2026-01-01"
    assert s[0]["value"] == pytest.approx(10000 - 10000 / 52 * 0.001)  # 첫날 1회 매수
    assert s[-1]["value"] == pytest.approx(10000 * 0.999)  # 52회 후 전액 투입, 이후 매수 없음
    assert len(s) == 400


def test_dca_skips_missing_close_to_next_day():
    start = date(2026, 1, 1)
    # 두 번째 매수일(1/8) 종가 없음 → 1/9(종가 200)에 매수
    closes = {start + timedelta(d): 100.0 for d in range(15) if d != 7}
    closes[date(2026, 1, 9)] = 200.0
    s = {r["date"]: r["value"] for r in dca_baseline(start, start + timedelta(14), closes, weeks=2, initial=1000.0)}
    assert "2026-01-08" not in s
    a = 500.0
    # 1/7: 1회 매수 @100 → 현금 500 + 수량 평가
    assert s["2026-01-07"] == pytest.approx(500 + a * 0.999)
    # 1/9: 두 번째 매수 @200, 첫 수량도 종가 200으로 평가
    qty = a * 0.999 / 100 + a * 0.999 / 200
    assert s["2026-01-09"] == pytest.approx(qty * 200)


def test_dca_buys_after_until_are_dropped():
    start = date(2026, 1, 1)
    closes = {start + timedelta(d): 100.0 for d in range(10)}
    s = dca_baseline(start, start + timedelta(9), closes, weeks=52)
    a = 10000 / 52  # 1/1, 1/8 두 번만 매수
    assert s[-1]["value"] == pytest.approx(10000 - 2 * a * 0.001)


def test_account_equity_series_hand_computed(state_db):
    from dashboard.backend.services.learning_account import place_order
    from dashboard.backend.services.learning_metrics import account_equity_series
    b = place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=1000.0, executed_at="2026-11-01T09:00:00+00:00")
    place_order("BTCUSDT", "sell", 120.0, R, {}, qty=b["qty"], executed_at="2026-11-03T09:00:00+00:00")
    for d, c in ((1, 100.0), (2, 110.0), (3, 120.0)):
        _candle("BTCUSDT", date(2026, 11, d), c)
    s = account_equity_series(date(2026, 10, 31), date(2026, 11, 4))
    assert [r["date"] for r in s] == ["2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    v = [r["value"] for r in s]
    assert v[0] == pytest.approx(10000.0)
    assert v[1] == pytest.approx(9000 + 9.99 * 100)  # 9999
    assert v[2] == pytest.approx(9000 + 9.99 * 110)  # 10098.9
    assert v[3] == pytest.approx(9000 + 1198.8 - 1.1988)  # 10197.6012
    assert v[4] == pytest.approx(10197.6012)


def test_performance_dca_null_when_ref_untracked(client):
    r = client.get("/api/learning/performance").json()
    assert r["dca"] is None
    assert r["dca_reason"] == "기준 종목(BTCUSDT) 캔들이 없습니다. 추적 목록에 추가하세요"
    assert r["usd_krw"] == 1400.0
    assert r["win_rate"] == {"n": 0, "win_rate": None}
    assert r["hit_rate"]["14"] == {"n": 0, "hit_rate": None, "partial_ratio": None}
    assert set(r["hit_rate"]) == {"14", "28"}
    assert isinstance(r["equity"], list) and r["equity"]


def test_performance_dca_series_when_tracked(client):
    today = datetime.now(timezone.utc).date()
    _candle("BTCUSDT", today, 100.0)
    r = client.get("/api/learning/performance").json()
    assert r["dca_reason"] is None
    assert r["dca"]["symbol"] == "BTCUSDT"
    assert r["dca"]["series"][-1]["date"] == today.isoformat()
    assert r["dca"]["series"][-1]["value"] == pytest.approx(10000 - 10000 / 52 * 0.001)
