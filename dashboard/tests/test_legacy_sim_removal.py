"""레거시 수동 모의투자(sim_*) 백업·삭제 및 학습 탭 테이블 생성 테스트."""

from __future__ import annotations

import json
import sqlite3

import pytest

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
