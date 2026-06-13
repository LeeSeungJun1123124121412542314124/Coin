"""paper_engine 단위·통합 테스트 — 순수 함수 + 임시 DB 격리."""

from __future__ import annotations

import pytest

from dashboard.backend.services import paper_engine as pe
from dashboard.backend.services.paper_engine import (
    compute_target,
    ensure_portfolios,
    liquidation_hit,
    realized_pnl,
    rebalance,
)


@pytest.fixture
def paper_db(tmp_path, monkeypatch):
    """임시 SQLite로 격리 (싱글톤 커넥션 리셋)."""
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()  # 스키마 초기화 (paper_* 포함)
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _px(close, high=None, low=None):
    return {"close": close, "high": high if high is not None else close, "low": low if low is not None else close}


# ── 순수 함수 ────────────────────────────────────────────────
def test_compute_target_deadband():
    assert compute_target(0.1, 9000, "복합방향") == (0.0, 0.0)


def test_compute_target_leverage_scaling():
    notional, lev = compute_target(0.5, 9000, "복합방향")
    assert lev == pytest.approx(1.5)          # min(0.5,1)*3
    assert notional == pytest.approx(1.5 * 3000)  # slot=9000/3
    _, lev_cap = compute_target(2.0, 9000, "복합방향")
    assert lev_cap == pytest.approx(3.0)      # 캡


def test_compute_target_short():
    notional, lev = compute_target(-1.0, 9000, "복합방향")
    assert notional < 0 and lev == pytest.approx(3.0)


def test_compute_target_buyhold_always_long_1x():
    """매수보유는 z 무시·deadband 무시, 항상 1배 롱."""
    assert compute_target(0.0, 9000, "매수보유") == (3000.0, 1.0)
    assert compute_target(-5.0, 9000, "매수보유") == (3000.0, 1.0)


def test_realized_pnl_long_short():
    assert realized_pnl("long", 10, 100, 110) == pytest.approx(100)
    assert realized_pnl("short", 10, 100, 110) == pytest.approx(-100)


def test_liquidation_hit():
    assert liquidation_hit("long", 67.0, high=90, low=60) is True
    assert liquidation_hit("short", 130.0, high=140, low=100) is True
    assert liquidation_hit("long", 67.0, high=90, low=70) is False
    assert liquidation_hit("long", None, high=90, low=10) is False


# ── 통합 (DB) ────────────────────────────────────────────────
def test_ensure_portfolios(paper_db):
    ensure_portfolios(["복합방향", "RSI"], seed=10000)
    with paper_db.get_db() as conn:
        rows = conn.execute("SELECT indicator, capital FROM paper_portfolios").fetchall()
    assert {r["indicator"] for r in rows} == {"복합방향", "RSI"}
    assert all(r["capital"] == 10000 for r in rows)


def test_rebalance_opens_and_marks_to_market(paper_db):
    ensure_portfolios(["복합방향"])
    r1 = rebalance("복합방향", {"BTC": 1.0}, {"BTC": _px(100)}, "2026-01-01T00:00:00")
    assert any("open:long" in t for t in r1["trades"])
    assert r1["equity"] == pytest.approx(10000 - 0.0005 * 10000, rel=1e-3)  # 시드 - 진입수수료

    # 가격 +10% → 미실현 이익으로 에쿼티 상승
    r2 = rebalance("복합방향", {"BTC": 1.0}, {"BTC": _px(110)}, "2026-01-02T00:00:00")
    assert r2["equity"] > r1["equity"]


def test_rebalance_short_profits_on_drop(paper_db):
    ensure_portfolios(["복합방향"])
    rebalance("복합방향", {"BTC": -1.0}, {"BTC": _px(100)}, "2026-01-01T00:00:00")
    r2 = rebalance("복합방향", {"BTC": -1.0}, {"BTC": _px(90)}, "2026-01-02T00:00:00")
    assert r2["equity"] > 10000  # 숏인데 하락 → 이익


def test_rebalance_liquidation(paper_db):
    ensure_portfolios(["복합방향"])
    rebalance("복합방향", {"BTC": 1.0}, {"BTC": _px(100)}, "2026-01-01T00:00:00")  # 롱 3배, liq≈67.7
    r2 = rebalance("복합방향", {"BTC": 1.0}, {"BTC": _px(60, high=65, low=60)}, "2026-01-02T00:00:00")
    assert any("liquidated" in t for t in r2["trades"])
    with paper_db.get_db() as conn:
        n_open = conn.execute(
            "SELECT COUNT(*) c FROM paper_positions WHERE status='open'"
        ).fetchone()["c"]
    assert r2["equity"] < 8000  # 청산 큰 손실


def test_benchmark_ignores_deadband(paper_db):
    ensure_portfolios(["매수보유"])
    r = rebalance("매수보유", {"BTC": 0.0}, {"BTC": _px(100)}, "2026-01-01T00:00:00")
    assert any("open:long" in t for t in r["trades"])  # z=0이어도 롱 진입
