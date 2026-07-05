from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.db.connection import _init_schema


CBOE_DAILY_HTML = """
<script>
self.__next_f.push([1,"selectedDate\":\"2026-07-02\",\"minDate\":\"2019-10-07\""])
</script>
<table>
  <tbody>
    <tr><td>TOTAL PUT/CALL RATIO</td><td>0.79</td></tr>
    <tr><td>INDEX PUT/CALL RATIO</td><td>0.97</td></tr>
    <tr><td>EQUITY PUT/CALL RATIO</td><td>0.53</td></tr>
  </tbody>
</table>
"""


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def test_parse_cboe_daily_statistics_html_extracts_selected_date_and_ratios() -> None:
    from dashboard.backend.collectors.cboe import parse_putcall_html

    assert parse_putcall_html(CBOE_DAILY_HTML) == {
        "date": "2026-07-02",
        "total_pc": 0.79,
        "equity_pc": 0.53,
        "index_pc": 0.97,
    }


def test_parse_cboe_daily_statistics_html_returns_none_without_ratios() -> None:
    from dashboard.backend.collectors.cboe import parse_putcall_html

    assert parse_putcall_html("<html><body>No data</body></html>") is None


@pytest.mark.asyncio
async def test_collect_putcall_upserts_latest_row(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_putcall

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_putcall():
        return {
            "date": "2026-07-02",
            "total_pc": 0.79,
            "equity_pc": 0.53,
            "index_pc": 0.97,
        }

    monkeypatch.setattr(collect_putcall, "get_db", fake_get_db)
    monkeypatch.setattr(collect_putcall, "fetch_putcall", fake_fetch_putcall)
    monkeypatch.setattr(
        collect_putcall,
        "_utc_now",
        lambda: datetime(2026, 7, 3, 0, 30, tzinfo=timezone.utc),
        raising=False,
    )

    await collect_putcall.collect_putcall()
    await collect_putcall.collect_putcall()

    rows = conn.execute(
        "SELECT date, total_pc, equity_pc, index_pc, updated_at FROM cboe_putcall"
    ).fetchall()
    assert [dict(row) for row in rows] == [{
        "date": "2026-07-02",
        "total_pc": 0.79,
        "equity_pc": 0.53,
        "index_pc": 0.97,
        "updated_at": "2026-07-03T00:30:00+00:00",
    }]


@pytest.mark.asyncio
async def test_collect_putcall_skips_empty_market_holiday_response(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_putcall

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_putcall():
        return None

    monkeypatch.setattr(collect_putcall, "get_db", fake_get_db)
    monkeypatch.setattr(collect_putcall, "fetch_putcall", fake_fetch_putcall)

    await collect_putcall.collect_putcall()

    count = conn.execute("SELECT COUNT(*) FROM cboe_putcall").fetchone()[0]
    assert count == 0


def test_putcall_api_returns_sorted_records_and_stale_flag(monkeypatch) -> None:
    from dashboard.backend.api import volume_routes

    conn = _memory_conn()
    conn.executemany(
        """INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("2026-07-01", 0.84, 0.61, 1.12, "2026-07-01T22:40:00+00:00"),
            ("2026-07-02", 0.79, 0.53, 0.97, "2026-07-02T22:40:00+00:00"),
        ],
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(volume_routes, "get_db", fake_get_db)
    monkeypatch.setattr(
        volume_routes,
        "_utc_now",
        lambda: datetime(2026, 7, 3, 20, 0, tzinfo=timezone.utc),
        raising=False,
    )

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/putcall?days=2")

    assert response.status_code == 200
    assert response.json() == {
        "stale": False,
        "records": [
            {"date": "2026-07-01", "total_pc": 0.84, "equity_pc": 0.61, "index_pc": 1.12},
            {"date": "2026-07-02", "total_pc": 0.79, "equity_pc": 0.53, "index_pc": 0.97},
        ],
    }


def test_putcall_api_marks_data_stale_after_48_hours(monkeypatch) -> None:
    from dashboard.backend.api import volume_routes

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("2026-07-02", 0.79, 0.53, 0.97, "2026-07-02T22:40:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(volume_routes, "get_db", fake_get_db)
    monkeypatch.setattr(
        volume_routes,
        "_utc_now",
        lambda: datetime(2026, 7, 5, 23, 0, tzinfo=timezone.utc),
        raising=False,
    )

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/putcall?days=90")

    assert response.status_code == 200
    assert response.json()["stale"] is True


def test_putcall_api_limits_days_to_90() -> None:
    from dashboard.backend.api import volume_routes

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/putcall?days=91")

    assert 400 <= response.status_code < 500


def test_collect_putcall_job_is_registered_at_utc_2230() -> None:
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")

    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())

    job = scheduler.get_job("collect_putcall")
    assert job is not None
    assert str(job.trigger) == "cron[day_of_week='mon-fri', hour='22', minute='30']"
