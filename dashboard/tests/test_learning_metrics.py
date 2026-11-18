"""적중률·승률 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

import pytest

from dashboard.backend.services.learning_metrics import hit_rate, win_rate

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


def seed_reviews(pairs, horizon=14):
    """(suggested, confirmed) 쌍마다 포지션과 복기 행을 직접 삽입."""
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        for sug, conf in pairs:
            pid = conn.execute(
                "INSERT INTO learning_positions(symbol, opened_at, entry_phase, first_entry_price, status)"
                " VALUES ('BTCUSDT', '2026-11-01T00:00:00+00:00', 'markup', 100, 'open')").lastrowid
            conn.execute(
                "INSERT INTO learning_reviews(position_id, horizon_days, suggested, confirmed, reason, close_price,"
                " judged_at) VALUES (?,?,?,?,?,?,?)",
                (pid, horizon, sug, conf, "사유" if conf else None, 100.0, "2026-11-20T00:00:00+00:00"))


def test_hit_rate_excludes_unclear_counts_partial_separately(state_db):
    seed_reviews([("hit", "hit"), ("partial", "partial"), ("miss", "miss"), (None, None), ("hit", None)])
    assert hit_rate(14) == {"n": 3, "hit_rate": pytest.approx(1 / 3), "partial_ratio": pytest.approx(1 / 3)}


def test_hit_rate_n0_is_none(state_db):
    assert hit_rate(14) == {"n": 0, "hit_rate": None, "partial_ratio": None}


def test_hit_rate_filters_by_horizon(state_db):
    seed_reviews([("hit", "hit")], horizon=28)
    assert hit_rate(14) == {"n": 0, "hit_rate": None, "partial_ratio": None}
    assert hit_rate(28)["n"] == 1


def test_win_rate_closed_only(state_db):
    from dashboard.backend.services.learning_account import place_order
    a = place_order("AAAUSDT", "buy", 100.0, R, {}, usdt_amount=1000.0)  # 승
    place_order("AAAUSDT", "sell", 120.0, R, {}, qty=a["qty"])
    b = place_order("BBBUSDT", "buy", 100.0, R, {}, usdt_amount=1000.0)  # 패
    place_order("BBBUSDT", "sell", 80.0, R, {}, qty=b["qty"])
    place_order("CCCUSDT", "buy", 100.0, R, {}, usdt_amount=500.0)  # 열린 포지션은 제외
    assert win_rate() == {"n": 2, "win_rate": 0.5}


def test_win_rate_empty(state_db):
    assert win_rate() == {"n": 0, "win_rate": None}
