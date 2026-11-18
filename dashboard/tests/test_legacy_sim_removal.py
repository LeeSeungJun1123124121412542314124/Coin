"""레거시 수동 모의투자(sim_*) 백업·삭제 및 학습 탭 테이블 생성 테스트."""

from __future__ import annotations

import json
import sqlite3

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SIM_TABLES = (
    "sim_predictions", "sim_positions", "sim_settlements",
    "sim_funding_events", "sim_account_resets",
)


@pytest.fixture
def conn_module(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "crypto.db"))
    monkeypatch.setattr(connection, "_conn", None)
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def test_legacy_tables_backed_up_and_dropped(tmp_path, conn_module):
    raw = sqlite3.connect(tmp_path / "crypto.db")
    raw.execute("CREATE TABLE sim_accounts (id INTEGER PRIMARY KEY, market TEXT, capital REAL)")
    raw.execute("INSERT INTO sim_accounts VALUES (1, 'crypto', 10000)")
    for t in _SIM_TABLES:
        raw.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)")
    raw.commit()
    raw.close()

    conn = conn_module.get_connection()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(n.startswith("sim_") for n in names)
    assert {"learning_candles", "learning_fills", "learning_reviews"} <= names
    backups = list((tmp_path / "backups").glob("legacy_sim_backup_*.json"))
    assert len(backups) == 1
    data = json.loads(backups[0].read_text(encoding="utf-8"))
    assert data["sim_accounts"][0]["capital"] == 10000


def test_no_legacy_tables_no_backup(tmp_path, conn_module):
    conn = conn_module.get_connection()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(n.startswith("sim_") for n in names)
    assert not (tmp_path / "backups").exists() or not list((tmp_path / "backups").glob("*.json"))


@pytest.mark.parametrize("method,path", [
    ("get", "/api/sim/accounts"),
    ("get", "/api/sim/predictions"),
    ("get", "/api/sim/scorecard"),
    ("get", "/api/sim/signals"),
    ("get", "/api/sim/macro-context"),
    ("get", "/api/sim/projection"),
    ("get", "/api/sim/win-rate-analysis"),
])
def test_legacy_endpoints_404(method, path):
    from dashboard.backend.api.sim_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    assert getattr(TestClient(app), method)(path).status_code == 404


def test_legacy_jobs_not_registered():
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")
    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())

    assert scheduler.get_job("settle_predictions") is None
    assert scheduler.get_job("sim_funding") is None


def test_deleted_paths_absent_from_router():
    from dashboard.backend.api.sim_routes import router

    deleted = {
        "/sim/accounts", "/sim/accounts/{market}/reset", "/sim/predictions",
        "/sim/predictions/{prediction_id}", "/sim/scorecard", "/sim/scorecard/by-indicator",
        "/sim/positions/{position_id}", "/sim/projection", "/sim/signals",
        "/sim/macro-context", "/sim/win-rate-analysis",
    }
    assert {r.path for r in router.routes}.isdisjoint(deleted)
