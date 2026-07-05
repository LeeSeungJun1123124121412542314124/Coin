from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import sqlite3

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dashboard.backend.db.connection import _init_schema


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _series(start: float, step: float = 1.0, days: int = 320) -> pd.Series:
    index = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.Series([start + i * step for i in range(days)], index=index)


def _sources() -> dict[str, pd.Series]:
    return {
        "close": _series(100),
        "net_liquidity": _series(1000, 2),
        "tga": _series(100, 0.5),
        "dxy": _series(90, 0.01),
        "ust10y": _series(4, 0.001),
        "vix": _series(15, 0.02),
        "mvrv": _series(1.5, 0.001),
        "active_addr": _series(10000, 3),
    }


def _history(days: int = 320) -> list[dict]:
    start = date(2025, 1, 1)
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "close": 100.0 + i}
        for i in range(days)
    ]


def test_direction_from_z_uses_plan_thresholds() -> None:
    from dashboard.backend.jobs.index_shadow import direction_from_z

    assert direction_from_z(0.5) == "long"
    assert direction_from_z(-0.5) == "short"
    assert direction_from_z(0.49) == "neutral"
    assert direction_from_z(None) == "neutral"


def test_build_index_shadow_records_returns_indicators_plus_composite() -> None:
    from dashboard.backend.jobs.index_shadow import build_index_shadow_records

    records = build_index_shadow_records("^GSPC", _history(), _sources(), "2026-07-05T00:00:00+00:00")

    assert len(records) == 8
    assert {record["indicator"] for record in records} == {
        "RSI",
        "볼린저밴드",
        "과열회귀",
        "VIX",
        "순유동성",
        "긴축환경",
        "유동성",
        "복합",
    }
    assert {record["symbol"] for record in records} == {"^GSPC"}
    assert {record["date"] for record in records} == {_history()[-1]["date"]}
    assert all(record["direction"] in {"long", "short", "neutral"} for record in records)


@pytest.mark.asyncio
async def test_judge_index_shadow_upserts_two_symbols_and_is_idempotent(monkeypatch) -> None:
    from dashboard.backend.jobs import index_shadow

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_index_history(symbol: str, days: int = 365, range: str | None = None):
        return _history()

    monkeypatch.setattr(index_shadow, "get_db", fake_get_db)
    monkeypatch.setattr(index_shadow, "get_sources", lambda cache_path: _sources())
    monkeypatch.setattr(index_shadow, "fetch_index_history", fake_fetch_index_history)
    monkeypatch.setattr(
        index_shadow,
        "_utc_now",
        lambda: datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc),
        raising=False,
    )

    await index_shadow.judge_index_shadow()
    await index_shadow.judge_index_shadow()

    rows = conn.execute(
        """SELECT symbol, indicator, direction
           FROM index_shadow_judgments
           ORDER BY symbol, indicator"""
    ).fetchall()
    assert len(rows) == 16
    assert {row["symbol"] for row in rows} == {"^KS11", "^GSPC"}
    assert {row["direction"] for row in rows} <= {"long", "short", "neutral"}


@pytest.mark.asyncio
async def test_settle_index_shadow_fills_due_horizon(monkeypatch) -> None:
    from dashboard.backend.jobs import index_shadow

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO index_shadow_judgments
           (date, symbol, indicator, z, direction, price, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-01-01", "^GSPC", "복합", 0.8, "long", 100.0, "2026-01-01T22:00:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_index_history(symbol: str, days: int = 365, range: str | None = None):
        return [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-08", "close": 102.0},
        ]

    monkeypatch.setattr(index_shadow, "get_db", fake_get_db)
    monkeypatch.setattr(index_shadow, "fetch_index_history", fake_fetch_index_history)
    monkeypatch.setattr(index_shadow, "_today", lambda: date(2026, 1, 8), raising=False)

    await index_shadow.settle_index_shadow()

    row = conn.execute(
        "SELECT price_after_7d, result_7d FROM index_shadow_judgments"
    ).fetchone()
    assert dict(row) == {"price_after_7d": 102.0, "result_7d": "hit"}


def test_index_shadow_jobs_are_registered_at_utc_0810_and_0820() -> None:
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")

    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())

    judge_job = scheduler.get_job("judge_index_shadow")
    settle_job = scheduler.get_job("settle_index_shadow")
    assert judge_job is not None
    assert settle_job is not None
    assert str(judge_job.trigger) == "cron[day_of_week='mon-fri', hour='8', minute='10']"
    assert str(settle_job.trigger) == "cron[day_of_week='mon-fri', hour='8', minute='20']"
