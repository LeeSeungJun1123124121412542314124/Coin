"""학습 모의 계좌·주문 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

import json

import pytest

R = {"phase": "markup",
     "ichimoku": {"cloud_position": "above", "tk_cross": "golden", "chikou": "above", "future_cloud": "bullish"}}


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


def test_buy_sell_fee_math(state_db):
    from dashboard.backend.services.learning_account import get_account, holdings, open_positions, place_order
    place_order("BTCUSDT", "buy", 50000.0, R, {}, usdt_amount=1000.0)
    assert get_account()["cash_usdt"] == pytest.approx(9000.0)
    pos = holdings({"BTCUSDT": 50000.0}, 1400.0)["positions"][0]
    assert pos["qty"] == pytest.approx(999.0 / 50000.0)
    assert pos["avg_cost"] == pytest.approx(1000.0 / (999.0 / 50000.0))
    place_order("BTCUSDT", "sell", 55000.0, R, {}, qty=pos["qty"])
    assert get_account()["cash_usdt"] == pytest.approx(9000 + 999 / 50000 * 55000 * 0.999)
    assert open_positions() == []


def test_full_sell_closes_position_and_stores_times(state_db):
    from dashboard.backend.db.connection import get_db
    from dashboard.backend.services.learning_account import place_order
    place_order("BTCUSDT", "buy", 100.0, R, {"a": 1}, usdt_amount=100.0, executed_at="2026-01-01T00:00:00+00:00",
                detected={"x": 1})
    r = place_order("BTCUSDT", "sell", 100.0, R, {}, qty=0.999, executed_at="2026-01-02T00:00:00+00:00")
    with get_db() as conn:
        p = conn.execute("SELECT * FROM learning_positions WHERE id=?", (r["position_id"],)).fetchone()
        fills = conn.execute("SELECT * FROM learning_fills ORDER BY id").fetchall()
    assert p["status"] == "closed" and p["closed_at"] == "2026-01-02T00:00:00+00:00"
    assert p["opened_at"] == "2026-01-01T00:00:00+00:00" and p["first_entry_price"] == 100.0
    assert p["entry_phase"] == "markup"
    assert fills[0]["usdt_amount"] == pytest.approx(100.0) and fills[0]["fee_usdt"] == pytest.approx(0.1)
    assert json.loads(fills[0]["detected_json"]) == {"x": 1}
    assert json.loads(fills[0]["snapshot_json"]) == {"a": 1}
    assert fills[1]["usdt_amount"] == pytest.approx(99.9) and fills[1]["fee_usdt"] == pytest.approx(0.0999)


def test_second_buy_joins_open_position(state_db):
    from dashboard.backend.services.learning_account import holdings, open_positions, place_order
    a = place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=1000.0)
    b = place_order("BTCUSDT", "buy", 200.0, R, {}, usdt_amount=1000.0)
    assert a["position_id"] == b["position_id"] and len(open_positions()) == 1
    pos = holdings({"BTCUSDT": 200.0}, None)["positions"][0]
    assert pos["qty"] == pytest.approx(9.99 + 4.995)
    assert pos["avg_cost"] == pytest.approx(2000.0 / (9.99 + 4.995))
    assert pos["market_value"] == pytest.approx(pos["qty"] * 200.0)
    assert pos["unrealized_pnl"] == pytest.approx(pos["qty"] * (200.0 - pos["avg_cost"]))


def test_overspend_and_oversell_rejected(state_db):
    from dashboard.backend.services.learning_account import place_order
    from dashboard.backend.services.learning_settings import LearningError
    with pytest.raises(LearningError):
        place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=10000.01)
    place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=1000.0)
    with pytest.raises(LearningError):
        place_order("BTCUSDT", "sell", 100.0, R, {}, qty=9.99 + 0.01)
    with pytest.raises(LearningError):
        place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=0)
    with pytest.raises(LearningError):
        place_order("BTCUSDT", "sell", 100.0, R, {}, qty=None)


def test_sell_without_position_rejected(state_db):
    from dashboard.backend.services.learning_account import place_order
    from dashboard.backend.services.learning_settings import LearningError
    with pytest.raises(LearningError):
        place_order("BTCUSDT", "sell", 100.0, R, {}, qty=1.0)


def test_krw_shown(state_db):
    from dashboard.backend.services.learning_account import holdings
    assert holdings({}, 1400.0)["equity_krw"] == pytest.approx(10000 * 1400)
    assert holdings({}, None)["equity_krw"] is None


def test_missing_price_gives_equity_none(state_db):
    from dashboard.backend.services.learning_account import holdings, place_order
    place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=1000.0)
    h = holdings({}, 1400.0)
    p = h["positions"][0]
    assert p["market_value"] is None and p["unrealized_pnl"] is None
    assert h["equity_usdt"] is None and h["equity_krw"] is None
    h2 = holdings({"BTCUSDT": 100.0}, 1400.0)
    assert h2["equity_usdt"] == pytest.approx(9000.0 + 9.99 * 100.0)


def test_get_account_created_once(state_db):
    from dashboard.backend.services.learning_account import get_account
    a = get_account()
    assert a["initial_usdt"] == 10000.0 and a["cash_usdt"] == 10000.0 and a["started_at"]
    assert get_account()["started_at"] == a["started_at"]


def _position_qty(position_id: int) -> float:
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        return conn.execute(
            "SELECT SUM(CASE side WHEN 'buy' THEN qty ELSE -qty END) FROM learning_fills WHERE position_id=?",
            (position_id,)).fetchone()[0]


# 화면은 보유 수량을 소수 8자리로 반올림해 보여 준다 — 그 값을 그대로 매도해도 전량 청산돼야 한다 (R18)
@pytest.mark.parametrize("amount,price", [
    (100.0, 64457.67), (250.0, 3456.78), (1000.0, 187.43), (37.5, 0.5234), (500.0, 0.00001234), (777.77, 98765.43),
])
def test_sell_displayed_qty_closes_position(state_db, amount, price):
    from dashboard.backend.services.learning_account import holdings, open_positions, place_order
    buy = place_order("BTCUSDT", "buy", price, R, {}, usdt_amount=amount)
    held = holdings({}, None)["positions"][0]["qty"]
    r = place_order("BTCUSDT", "sell", price, R, {}, qty=round(held, 8))
    assert open_positions() == []
    assert r["qty"] == held and _position_qty(buy["position_id"]) == 0.0


def test_sell_held_minus_tiny_closes(state_db):
    from dashboard.backend.services.learning_account import holdings, open_positions, place_order
    place_order("BTCUSDT", "buy", 64457.67, R, {}, usdt_amount=100.0)
    held = holdings({}, None)["positions"][0]["qty"]
    r = place_order("BTCUSDT", "sell", 64457.67, R, {}, qty=held - 1e-12)
    assert open_positions() == [] and r["qty"] == held


def test_partial_sell_beyond_tolerance_keeps_position(state_db):
    from dashboard.backend.services.learning_account import holdings, open_positions, place_order
    from dashboard.backend.services.learning_settings import LearningError
    place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=100.0)
    held = holdings({}, None)["positions"][0]["qty"]
    with pytest.raises(LearningError):
        place_order("BTCUSDT", "sell", 100.0, R, {}, qty=held + 1e-7)
    place_order("BTCUSDT", "sell", 100.0, R, {}, qty=held - 1e-7)
    assert len(open_positions()) == 1


def test_buy_displayed_cash_rounded_up_succeeds(state_db):
    from dashboard.backend.services.learning_account import get_account, place_order
    from dashboard.backend.services.learning_settings import LearningError
    place_order("BTCUSDT", "buy", 100.0, R, {}, usdt_amount=100.004)
    cash = get_account()["cash_usdt"]
    shown = round(cash, 2)
    assert shown > cash  # 9899.996 → 9900.00 으로 올림 표시
    r = place_order("ETHUSDT", "buy", 100.0, R, {}, usdt_amount=shown)
    assert r["cash_usdt"] == 0.0 and get_account()["cash_usdt"] == 0.0
    assert r["fee_usdt"] == pytest.approx(cash * 0.001)
    for amount in (0.005, 0.004):  # 현금 0이면 허용오차 안이어도 거부 (수량 0 체결 방지)
        with pytest.raises(LearningError):
            place_order("ETHUSDT", "buy", 100.0, R, {}, usdt_amount=amount)
