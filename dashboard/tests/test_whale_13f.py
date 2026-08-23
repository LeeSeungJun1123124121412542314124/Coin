from __future__ import annotations

from contextlib import contextmanager
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.db.connection import _init_schema


@contextmanager
def _fake_db(conn):
    yield conn


def test_us_13f_api_returns_latest_four_quarters_without_puts_or_non_slots(monkeypatch) -> None:
    from dashboard.backend.api import whale_routes

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    monkeypatch.setattr(whale_routes, "get_db", lambda: _fake_db(conn))
    conn.execute("DELETE FROM stock_slots WHERE market='us'")
    conn.executemany(
        "INSERT INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES ('us', ?, ?, ?, NULL)",
        [(1, "AAPL", "애플"), (2, "MSFT", "마이크로소프트")],
    )
    rows = [
        ("a1", 0, "Fund A", 1, "AAPL", "APPLE INC", "2026-06-30", 10, 300, None),
        ("a2", 0, "Fund B", 2, "AAPL", "APPLE INC", "2026-06-30", 20, 200, "Call"),
        ("a3", 0, "Fund A", 1, "AAPL", "APPLE INC", "2026-03-31", 10, 400, None),
        ("m1", 0, "Fund A", 1, "MSFT", "MICROSOFT CORP", "2026-06-30", 10, 100, None),
        ("put", 0, "Fund A", 1, "MSFT", "MICROSOFT CORP", "2026-06-30", 99, 9999, "Put"),
        ("old1", 0, "Fund A", 1, "AAPL", "APPLE INC", "2025-12-31", 1, 30, None),
        ("old2", 0, "Fund A", 1, "AAPL", "APPLE INC", "2025-09-30", 1, 20, None),
        ("too-old", 0, "Fund A", 1, "AAPL", "APPLE INC", "2025-06-30", 1, 10, None),
        ("non-slot", 0, "Fund A", 1, "NVDA", "NVIDIA CORP", "2026-06-30", 1, 777, None),
    ]
    conn.executemany(
        """INSERT INTO us_13f_holdings
           (accession_no, seq, institution, cik, ticker, issuer_name, quarter, shares, value_usd, put_call)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )

    app = FastAPI()
    app.include_router(whale_routes.router, prefix="/api")
    body = TestClient(app).get("/api/whale/us-13f-holdings").json()

    assert body["quarters"] == ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]
    assert {row["accession_no"] for row in body["holdings"]} == {"a1", "a2", "a3", "m1", "old1", "old2"}
    assert all(row["put_call"] != "Put" for row in body["holdings"])
    assert body["summaries"] == [
        {"ticker": "AAPL", "latest_quarter": "2026-06-30", "latest_value": 500.0, "prev_value": 400.0, "qoq_change": 25.0},
        {"ticker": "MSFT", "latest_quarter": "2026-06-30", "latest_value": 100.0, "prev_value": 0.0, "qoq_change": None},
    ]
