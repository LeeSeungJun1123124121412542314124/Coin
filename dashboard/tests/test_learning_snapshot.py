"""체결 스냅샷 테스트 — DB 값만 읽음 (네트워크 없음)."""

from __future__ import annotations

import pytest

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.learning_snapshot import build_snapshot


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


def _seed(metric, scope, as_of, value, source):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO learning_metrics(metric, scope, as_of, value, source) VALUES (?,?,?,?,?)",
            (metric, scope, as_of, value, source),
        )


def test_snapshot_non_btc_includes_btc_context(state_db) -> None:
    _seed("mvrv", "BTC", "2026-11-16", 1.1, "coinmetrics")
    _seed("mvrv", "BTC", "2026-11-17", 1.2, "coinmetrics")
    _seed("funding_rate", "SOLUSDT", "2026-11-18", 0.0001, "binance-futures")
    _seed("sol_tvl", "SOL", "2026-11-17", 4.7e9, "defillama")
    snap = build_snapshot("SOLUSDT")
    assert snap["symbol"] == "SOLUSDT"
    assert snap["items"]["mvrv"] == {"value": 1.2, "as_of": "2026-11-17", "source": "coinmetrics"}
    assert snap["items"]["funding_rate"]["value"] == 0.0001 and "sol_tvl" in snap["items"]
    assert snap["items"]["sopr"]["value"] is None and snap["items"]["sopr"]["reason"]
    assert "sol_tvl" not in build_snapshot("ETHUSDT")["items"]


def test_snapshot_missing_reason_uses_latest_failure(state_db) -> None:
    with get_db() as conn:
        conn.execute("INSERT INTO learning_collection_runs(source, run_at, status, reason) "
                     "VALUES ('bgeometrics','t','rate_limited','한도 초과')")
        conn.execute("INSERT INTO learning_collection_runs(source, run_at, status, reason) "
                     "VALUES ('fred','t','ok',NULL)")
    items = build_snapshot("BTCUSDT")["items"]
    assert items["sopr"] == {"value": None, "reason": "한도 초과"}
    assert items["tga"] == {"value": None, "reason": "수집된 값 없음"}
