"""학습 일지·복기 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ICH = {"cloud_position": "above", "tk_cross": "golden", "chikou": "above", "future_cloud": "bullish"}
R = {"phase": "markup", "ichimoku": _ICH, "memo": "진입 근거"}
UNCLEAR = {"phase": "unclear", "ichimoku": _ICH}


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


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _candle(symbol, d: date, close):
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO learning_candles(symbol, interval, open_time, open, high, low, close, volume)"
            " VALUES (?, '1d', ?, ?, ?, ?, ?, 1)", (symbol, _ms(d), close, close, close, close))


def _scenario(rationale=R):
    """11/01 1000 USDT 매수 @100, 11/10 절반 매도 @110, 11/15 종가 120."""
    from dashboard.backend.services.learning_account import place_order
    b = place_order("BTCUSDT", "buy", 100.0, rationale, {"s": 1}, usdt_amount=1000.0,
                    executed_at="2026-11-01T09:00:00+00:00", detected={"d": 1})
    place_order("BTCUSDT", "sell", 110.0, rationale, {}, qty=4.995, executed_at="2026-11-10T09:00:00+00:00")
    _candle("BTCUSDT", date(2026, 11, 15), 120.0)
    return b["position_id"]


def test_review_pnl_and_hold_return(state_db):
    from dashboard.backend.services.learning_review import review_position
    pid = _scenario()
    r = review_position(pid, 14, today=date(2026, 11, 20))
    assert r["status"] == "ready"
    assert r["close_price"] == 120.0
    assert r["hold_return_pct"] == pytest.approx(20.0)
    assert r["pnl_usdt"] == pytest.approx(148.30055)
    assert r["suggested"] == "hit"
    assert r["confirmed"] is None and r["reason"] is None
    assert r["rationale"] == {"phase": "markup", "ichimoku": _ICH, "detected": {"d": 1}, "memo": "진입 근거"}


def test_pnl_excludes_fills_after_due_date(state_db):
    from dashboard.backend.services.learning_account import place_order
    from dashboard.backend.services.learning_review import review_position
    pid = _scenario()
    place_order("BTCUSDT", "buy", 130.0, R, {}, usdt_amount=100.0, executed_at="2026-11-16T00:00:00+00:00")
    r = review_position(pid, 14, today=date(2026, 11, 20))
    assert r["pnl_usdt"] == pytest.approx(148.30055)


def test_review_pending_when_no_candle(state_db):
    from dashboard.backend.db.connection import get_db
    from dashboard.backend.services.learning_review import review_position
    pid = _scenario()
    r = review_position(pid, 28, today=date(2026, 12, 30))  # 기준일 11/29 캔들 없음
    assert r == {"status": "pending", "due": "2026-11-29"}
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM learning_reviews").fetchone()[0] == 0


def test_review_pending_when_due_in_future(state_db):
    from dashboard.backend.services.learning_review import review_position
    pid = _scenario()
    assert review_position(pid, 14, today=date(2026, 11, 14)) == {"status": "pending", "due": "2026-11-15"}


def test_review_upserts_suggested(state_db):
    from dashboard.backend.db.connection import get_db
    from dashboard.backend.services.learning_review import review_position
    pid = _scenario()
    review_position(pid, 14, today=date(2026, 11, 20))
    review_position(pid, 14, today=date(2026, 11, 20))
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM learning_reviews").fetchall()
    assert len(rows) == 1
    assert rows[0]["suggested"] == "hit" and rows[0]["close_price"] == 120.0 and rows[0]["judged_at"]


def test_review_unclear_stores_null_suggested(state_db):
    from dashboard.backend.db.connection import get_db
    from dashboard.backend.services.learning_review import review_position
    pid = _scenario(UNCLEAR)
    r = review_position(pid, 14, today=date(2026, 11, 20))
    assert r["status"] == "ready" and r["suggested"] is None
    with get_db() as conn:
        assert conn.execute("SELECT suggested FROM learning_reviews").fetchone()[0] is None


def test_confirm_overrides_and_persists(state_db):
    from dashboard.backend.services.learning_review import confirm_review, review_position
    pid = _scenario()
    review_position(pid, 14, today=date(2026, 11, 20))
    c = confirm_review(pid, 14, "miss", "  국면을 잘못 봤다  ")
    assert c["suggested"] == "hit" and c["confirmed"] == "miss" and c["reason"] == "국면을 잘못 봤다"
    # 재복기해도 확정값 유지
    r = review_position(pid, 14, today=date(2026, 11, 20))
    assert r["confirmed"] == "miss" and r["reason"] == "국면을 잘못 봤다" and r["suggested"] == "hit"


def test_confirm_rejections(state_db):
    from dashboard.backend.services.learning_review import confirm_review, review_position
    from dashboard.backend.services.learning_settings import LearningError
    pid = _scenario()
    with pytest.raises(LearningError):  # 준비되지 않음(행 없음)
        confirm_review(pid, 14, "hit", "사유")
    review_position(pid, 14, today=date(2026, 11, 20))
    for verdict, reason in [("bad", "사유"), ("hit", ""), ("hit", "   "), ("hit", "x" * 1001), ("hit", None)]:
        with pytest.raises(LearningError):
            confirm_review(pid, 14, verdict, reason)
    with pytest.raises(LearningError):
        confirm_review(pid, 7, "hit", "사유")
    confirm_review(pid, 14, "hit", "x" * 1000)


def test_confirm_rejected_for_unclear(state_db):
    from dashboard.backend.services.learning_review import confirm_review, review_position
    from dashboard.backend.services.learning_settings import LearningError
    pid = _scenario(UNCLEAR)
    review_position(pid, 14, today=date(2026, 11, 20))
    with pytest.raises(LearningError):
        confirm_review(pid, 14, "hit", "사유")


def test_journal_groups_fills_by_position(state_db):
    from dashboard.backend.services.learning_account import place_order
    from dashboard.backend.services.learning_review import journal
    pid = _scenario()
    place_order("ETHUSDT", "buy", 10.0, R, {"e": 1}, usdt_amount=100.0, executed_at="2026-11-12T00:00:00+00:00")
    j = journal()
    assert [e["position"]["symbol"] for e in j] == ["ETHUSDT", "BTCUSDT"]
    btc = j[1]
    assert btc["position"]["id"] == pid
    assert [f["side"] for f in btc["fills"]] == ["buy", "sell"]
    f0 = btc["fills"][0]
    assert f0["ichimoku"] == _ICH and f0["detected"] == {"d": 1} and f0["snapshot"] == {"s": 1}
    assert f0["memo"] == "진입 근거" and f0["phase"] == "markup"
    assert len(journal(limit=1)) == 1


def test_api_paths(client):
    pid = _scenario()
    j = client.get("/api/learning/journal")
    assert j.status_code == 200 and len(j.json()) == 1
    # today 기본값(실제 UTC 오늘)은 11/18 이후이므로 14일차는 ready, 28일차는 캔들 없음 → pending
    g = client.get(f"/api/learning/reviews/{pid}")
    assert g.status_code == 200
    body = g.json()
    assert set(body) == {"14", "28"}
    assert body["14"]["status"] == "ready" and body["28"] == {"status": "pending", "due": "2026-11-29"}
    ok = client.post(f"/api/learning/reviews/{pid}/14/confirm", json={"verdict": "partial", "reason": "애매함"})
    assert ok.status_code == 200 and ok.json()["confirmed"] == "partial"
    assert client.post(f"/api/learning/reviews/{pid}/14/confirm",
                       json={"verdict": "bad", "reason": "r"}).status_code == 400
    assert client.post(f"/api/learning/reviews/{pid}/7/confirm",
                       json={"verdict": "hit", "reason": "r"}).status_code == 400
    assert client.post(f"/api/learning/reviews/{pid}/28/confirm",
                       json={"verdict": "hit", "reason": "r"}).status_code == 400  # pending
    assert client.get("/api/learning/reviews/9999").status_code == 404
    assert client.post("/api/learning/reviews/9999/14/confirm",
                       json={"verdict": "hit", "reason": "r"}).status_code == 404
