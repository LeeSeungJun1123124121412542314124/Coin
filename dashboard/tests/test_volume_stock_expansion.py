from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import sqlite3

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.db.connection import _init_schema


CNN_CURRENT_FIXTURE = {
    "fear_and_greed": {
        "score": "43.2",
        "rating": "Fear",
        "timestamp": "2026-07-03T20:15:00.000Z",
    }
}

CNN_HISTORY_FIXTURE = {
    "fear_and_greed_historical": {
        "data": [
            {"date": "2026-07-02", "value": 39, "rating": "Fear"},
            {"date": "2026-07-03", "value": 52, "rating": "Neutral"},
        ]
    }
}

NAVER_MARKET_VOLUME_HTML = """
<html>
  <body>
    <table>
      <tr>
        <th>날짜</th><th>체결가</th><th>전일비</th><th>등락률</th>
        <th>거래량(천주)</th><th>거래대금(백만)</th>
      </tr>
      <tr>
        <td>2026.07.03</td><td>3,054.28</td><td>10.10</td><td>+0.33%</td>
        <td>612,345</td><td>12,345,678</td>
      </tr>
      <tr>
        <td>2026.07.02</td><td>3,044.18</td><td>4.30</td><td>+0.14%</td>
        <td>512,345</td><td>9,876,543</td>
      </tr>
    </table>
  </body>
</html>
"""


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def test_parse_cnn_fear_greed_current_fixture() -> None:
    from dashboard.backend.collectors.cnn_fear_greed import parse_fear_greed_payload

    assert parse_fear_greed_payload(CNN_CURRENT_FIXTURE) == {
        "date": "2026-07-03",
        "value": 43.2,
        "rating": "Fear",
        "updated_at": "2026-07-03T20:15:00+00:00",
    }


def test_parse_cnn_fear_greed_history_fixture_falls_back_to_latest_point() -> None:
    from dashboard.backend.collectors.cnn_fear_greed import parse_fear_greed_payload

    assert parse_fear_greed_payload(CNN_HISTORY_FIXTURE) == {
        "date": "2026-07-03",
        "value": 52.0,
        "rating": "Neutral",
        "updated_at": "2026-07-03T00:00:00+00:00",
    }


def test_parse_naver_market_volume_html_converts_million_krw_to_trillion_krw() -> None:
    from dashboard.backend.collectors.naver_finance import parse_market_volume_html

    assert parse_market_volume_html(NAVER_MARKET_VOLUME_HTML) == [
        {"date": "2026-07-03", "value": 12.3457},
        {"date": "2026-07-02", "value": 9.8765},
    ]


def test_stock_fear_greed_api_returns_latest_row_and_stale_flag(monkeypatch) -> None:
    from dashboard.backend.api import volume_routes

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        ("2026-07-03", 43.2, "Fear", "2026-07-03T20:15:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(volume_routes, "get_db", fake_get_db)
    monkeypatch.setattr(
        volume_routes,
        "_utc_now",
        lambda: datetime(2026, 7, 3, 21, 0, tzinfo=timezone.utc),
        raising=False,
    )

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/stock-fear-greed")

    assert response.status_code == 200
    assert response.json() == {
        "value": 43.2,
        "rating": "Fear",
        "updated_at": "2026-07-03T20:15:00+00:00",
        "stale": False,
    }


def test_stock_fear_greed_api_marks_data_stale_after_two_hours(monkeypatch) -> None:
    from dashboard.backend.api import volume_routes

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        ("2026-07-03", 43.2, "Fear", "2026-07-03T20:15:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(volume_routes, "get_db", fake_get_db)
    monkeypatch.setattr(
        volume_routes,
        "_utc_now",
        lambda: datetime(2026, 7, 3, 22, 16, tzinfo=timezone.utc),
        raising=False,
    )

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/stock-fear-greed")

    assert response.status_code == 200
    assert response.json()["stale"] is True


def test_kr_market_volume_api_returns_sorted_records_and_stale_flag(monkeypatch) -> None:
    from dashboard.backend.api import volume_routes

    conn = _memory_conn()
    conn.executemany(
        """INSERT INTO kr_market_volume (date, kospi_value, kosdaq_value)
           VALUES (?, ?, ?)""",
        [
            ("2026-07-02", 9.8, 4.1),
            ("2026-07-03", 12.3, 5.2),
        ],
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(volume_routes, "get_db", fake_get_db)
    monkeypatch.setattr(volume_routes, "_kst_today", lambda: date(2026, 7, 5), raising=False)

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/kr-market-volume?days=2")

    assert response.status_code == 200
    assert response.json() == {
        "stale": False,
        "records": [
            {"date": "2026-07-02", "kospi_value": 9.8, "kosdaq_value": 4.1},
            {"date": "2026-07-03", "kospi_value": 12.3, "kosdaq_value": 5.2},
        ],
    }


def test_kr_market_volume_api_excludes_partial_rows_from_fresh_records(monkeypatch) -> None:
    from dashboard.backend.api import volume_routes

    conn = _memory_conn()
    conn.executemany(
        """INSERT INTO kr_market_volume (date, kospi_value, kosdaq_value)
           VALUES (?, ?, ?)""",
        [
            ("2026-07-02", 9.8, 4.1),
            ("2026-07-03", 12.3, None),
        ],
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(volume_routes, "get_db", fake_get_db)
    monkeypatch.setattr(volume_routes, "_kst_today", lambda: date(2026, 7, 5), raising=False)

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/kr-market-volume?days=30")

    assert response.status_code == 200
    assert response.json() == {
        "stale": False,
        "records": [
            {"date": "2026-07-02", "kospi_value": 9.8, "kosdaq_value": 4.1},
        ],
    }


def test_kr_market_volume_api_limits_days_to_30() -> None:
    from dashboard.backend.api import volume_routes

    app = FastAPI()
    app.include_router(volume_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/volume/kr-market-volume?days=31")

    assert 400 <= response.status_code < 500


@pytest.mark.asyncio
async def test_collect_stock_fear_greed_upserts_latest_row(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_stock_fear_greed

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_fear_greed():
        return {
            "date": "2026-07-03",
            "value": 43.2,
            "rating": "Fear",
            "updated_at": "2026-07-03T20:15:00+00:00",
        }

    monkeypatch.setattr(collect_stock_fear_greed, "get_db", fake_get_db)
    monkeypatch.setattr(collect_stock_fear_greed, "fetch_fear_greed", fake_fetch_fear_greed)

    await collect_stock_fear_greed.collect_stock_fear_greed()

    rows = conn.execute(
        "SELECT date, value, rating, updated_at FROM stock_fear_greed"
    ).fetchall()
    assert [dict(row) for row in rows] == [{
        "date": "2026-07-03",
        "value": 43.2,
        "rating": "Fear",
        "updated_at": "2026-07-03T20:15:00+00:00",
    }]


def test_stock_fear_greed_job_is_registered_hourly() -> None:
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")

    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())

    job = scheduler.get_job("collect_stock_fear_greed")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 3600
