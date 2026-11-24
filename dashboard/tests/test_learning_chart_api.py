"""학습 차트·주문 컨텍스트 API 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_DAY = 86_400_000
_T0 = 1_600_000_000_000 // _DAY * _DAY
_STATE_KEYS = {"cloud_position", "tk_cross", "chikou", "future_cloud"}


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
def client(state_db):
    from dashboard.backend.api.learning_routes import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _track(symbol="BTCUSDT"):
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        conn.execute("INSERT INTO learning_symbols(symbol) VALUES (?)", (symbol,))


def _insert(candles, symbol="BTCUSDT", interval="1d"):
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO learning_candles(symbol, interval, open_time, open, high, low, close, volume)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [(symbol, interval, c["open_time"], c["open"], c["high"], c["low"], c["close"], c["volume"])
             for c in candles],
        )


def _box_with_spring(n=120, spring_at=110):
    """폭 약 20% 박스 + spring_at번째 봉이 박스 하단을 이탈 후 복귀."""
    out = []
    for i in range(n):
        high, low = (110.0, 100.0) if i % 2 == 0 else (100.0, 90.0)
        if i == spring_at:
            high, low = 101.0, 80.0
        out.append({"open_time": _T0 + i * _DAY, "open": 100.0, "high": high,
                    "low": low, "close": 100.0, "volume": 10.0})
    return out


def test_chart_returns_all_keys(client):
    _track()
    _insert(_box_with_spring())
    r = client.get("/api/learning/chart", params={"symbol": "btcusdt", "interval": "1d", "limit": 100})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"candles", "ichimoku", "wyckoff", "pivots", "fib", "state", "settings", "indicators", "structure"}
    assert 0 < len(body["candles"]) <= 100
    assert set(body["state"]) == _STATE_KEYS


def test_chart_wyckoff_changes_with_width_pct(client):
    _track()
    _insert(_box_with_spring())
    url = "/api/learning/chart?symbol=BTCUSDT&interval=1d&limit=120"
    client.put("/api/learning/settings", json={"wyckoff": {"width_pct": 15}})
    assert client.get(url).json()["wyckoff"]["candidates"] == []
    client.put("/api/learning/settings", json={"wyckoff": {"width_pct": 25}})
    cands = client.get(url).json()["wyckoff"]["candidates"]
    assert len(cands) >= 1 and cands[0]["type"] == "spring"


def test_chart_untracked_404_and_bad_interval_422(client):
    r = client.get("/api/learning/chart", params={"symbol": "ETHUSDT", "interval": "1d"})
    assert r.status_code == 404 and "detail" in r.json()
    _track()
    assert client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": "15m"}).status_code == 422


def test_chart_empty_candles_returns_empty_structure(client):
    _track()
    r = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": "1d"})
    assert r.status_code == 200
    b = r.json()
    assert b["candles"] == [] and b["ichimoku"] == [] and b["pivots"] == [] and b["fib"] == []
    assert b["wyckoff"] == {"volume_spikes": [], "candidates": [], "current_box": None}
    assert b["state"] == {k: None for k in _STATE_KEYS}
    assert b["settings"]["wyckoff"]["n"] == 30
    assert b["structure"] is None


def test_chart_trims_to_first_candle(client):
    _track()
    # 지그재그 피벗이 생기도록 오르내리는 캔들 + 스프링
    candles = _box_with_spring(200, 190)
    for i, c in enumerate(candles):
        swing = 30.0 if (i // 20) % 2 else 0.0
        for k in ("open", "high", "low", "close"):
            c[k] += swing
    _insert(candles)
    b = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": "1d", "limit": 50}).json()
    assert len(b["candles"]) == 50
    t0 = b["candles"][0]["open_time"]
    assert all(r["time"] >= t0 for r in b["ichimoku"])
    assert len(b["ichimoku"]) == 50 + 26
    assert all(p["time"] >= t0 for p in b["pivots"])
    assert all(c["time"] >= t0 for c in b["wyckoff"]["candidates"])
    assert all(t >= t0 for t in b["wyckoff"]["volume_spikes"])


def test_order_context_has_state_keys(client):
    _track()
    _insert(_box_with_spring())
    r = client.get("/api/learning/order-context", params={"symbol": "BTCUSDT"})
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"ichimoku_state", "wyckoff_recent", "current_box"}
    assert set(b["ichimoku_state"]) == _STATE_KEYS


def test_order_context_wyckoff_recent_within_last_5_bars(client):
    _track()
    _insert(_box_with_spring(120, 118))  # 마지막 5봉 안의 스프링
    client.put("/api/learning/settings", json={"wyckoff": {"width_pct": 25}})
    b = client.get("/api/learning/order-context", params={"symbol": "BTCUSDT"}).json()
    assert [c["type"] for c in b["wyckoff_recent"]] == ["spring"]


def test_order_context_empty_and_untracked(client):
    assert client.get("/api/learning/order-context", params={"symbol": "BTCUSDT"}).status_code == 404
    _track()
    b = client.get("/api/learning/order-context", params={"symbol": "BTCUSDT"}).json()
    assert b == {"ichimoku_state": {k: None for k in _STATE_KEYS}, "wyckoff_recent": [], "current_box": None}
    assert client.get("/api/learning/order-context",
                      params={"symbol": "BTCUSDT", "interval": "15m"}).status_code == 422


def _flat_candles(n, interval="1d"):
    step = {"1h": 3_600_000, "4h": 14_400_000, "1d": _DAY, "1w": 7 * _DAY, "1M": 30 * _DAY}[interval]
    return [{"open_time": _T0 + i * step, "open": 100.0, "high": 105.0 + i % 3,
             "low": 95.0, "close": 100.0 + i % 2, "volume": 10.0} for i in range(n)]


@pytest.mark.parametrize("interval", ["1h", "4h", "1d", "1w", "1M"])
def test_chart_accepts_all_intervals(client, interval):
    _track()
    _insert(_flat_candles(60, interval), interval=interval)
    r = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": interval, "limit": 60})
    assert r.status_code == 200
    assert len(r.json()["candles"]) == 60


def test_chart_rejects_unknown_interval(client):
    _track()
    assert client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": "15m"}).status_code == 422


def test_stored_settings_get_new_threshold_defaults(client):
    import json

    from dashboard.backend.db.connection import get_db
    old = {"threshold_1d": 12, "threshold_4h": 6, "levels": [0.5]}
    with get_db() as conn:
        conn.execute("INSERT INTO learning_settings(key, value) VALUES (?, ?)",
                     ("elliott", json.dumps(old)))
    el = client.get("/api/learning/settings").json()["elliott"]
    assert (el["threshold_1h"], el["threshold_1w"], el["threshold_1M"]) == (3.0, 20.0, 30.0)
    assert (el["threshold_1d"], el["threshold_4h"]) == (12, 6)


def test_threshold_out_of_range_rejected(client):
    r = client.put("/api/learning/settings", json={"elliott": {"threshold_1M": 51}})
    assert r.status_code == 400


def test_short_monthly_history_returns_200(client):
    _track()
    _insert(_flat_candles(10, "1M"), interval="1M")
    r = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": "1M"})
    assert r.status_code == 200
    assert all(v is None for v in r.json()["state"].values())


def _trend(n):
    return [{"open_time": _T0 + i * _DAY, "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
             "close": 100.0 + i + (i % 3), "volume": 10.0} for i in range(n)]


def test_chart_indicators_empty_when_all_off(client):
    _track()
    _insert(_trend(60))
    body = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "limit": 30}).json()
    assert body["indicators"] == {}


def test_chart_indicators_only_enabled_and_visible(client):
    _track()
    _insert(_trend(200))
    client.put("/api/learning/settings", json={"indicators": {
        "ma": {"enabled": True, "periods": [5, 120]}, "rsi": {"enabled": True},
        "macd": {"enabled": True}, "bb": {"enabled": True}}})
    body = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "limit": 30}).json()
    ind = body["indicators"]
    assert set(ind) == {"ma", "bb", "rsi", "macd"}
    t0 = body["candles"][0]["open_time"]
    assert [m["period"] for m in ind["ma"]] == [5, 120]
    # 120봉 이평은 워밍업 덕에 보이는 30봉 전체가 채워진다
    assert len(ind["ma"][1]["points"]) == 30
    assert all(p["time"] >= t0 for p in ind["ma"][1]["points"])
    for key in ("bb", "rsi", "macd"):
        assert ind[key] and all(p["time"] >= t0 for p in ind[key])
    assert set(ind["bb"][0]) == {"time", "upper", "mid", "lower"}
    assert set(ind["macd"][0]) == {"time", "macd", "signal", "hist"}
    assert set(ind["rsi"][0]) == {"time", "value"}


def test_chart_indicators_short_history_no_error(client):
    _track()
    _insert(_trend(10))
    client.put("/api/learning/settings", json={"indicators": {"macd": {"enabled": True}}})
    body = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "limit": 30}).json()
    assert body["indicators"] == {"macd": []}


def test_chart_structure_uses_daily_as_htf_for_1h(client):
    _track()
    _insert(_flat_candles(80, "1h"), interval="1h")
    s = client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": "1h", "limit": 60}).json()["structure"]
    assert s["htf_interval"] == "1d"
    assert s["htf"]["insufficient"] is True  # 일봉 캔들이 없다
    assert set(s) == {"htf_interval", "htf", "ltf", "score", "label", "reasons", "htf_pts", "ltf_pts", "bonus"}
    assert 0 <= s["score"] <= 100 and s["htf"]["range"] == {"high": None, "low": None}


def test_chart_structure_htf_mapping_and_monthly_none(client):
    _track()
    _insert(_flat_candles(60, "1d"), interval="1d")
    _insert(_flat_candles(60, "1M"), interval="1M")
    get = lambda i: client.get("/api/learning/chart", params={"symbol": "BTCUSDT", "interval": i}).json()["structure"]  # noqa: E731
    assert get("1d")["htf_interval"] == "1w"
    assert get("1M")["htf_interval"] is None
