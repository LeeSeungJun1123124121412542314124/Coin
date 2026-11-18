"""보존 대상 /sim 엔드포인트(백테스트·튜닝·리더보드) 유지 확인 테스트."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()  # 스키마 생성
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def test_kept_routes_registered():
    from dashboard.backend.api.sim_routes import router

    paths = {r.path for r in router.routes}
    assert {
        "/sim/auto-backtest", "/sim/composite-backtest", "/sim/tune",
        "/sim/tune/{job_id}", "/sim/leaderboard", "/sim/leaderboard/{indicator}",
        "/sim/leaderboard/reset",
    } <= paths


def test_leaderboard_ok(state_db):
    from dashboard.backend.api.sim_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    assert client.get("/api/sim/leaderboard").status_code == 200
