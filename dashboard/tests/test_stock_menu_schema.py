"""주식 메뉴 확장용 DB 스키마 테스트."""

from __future__ import annotations

import sqlite3

import pytest

from dashboard.backend.db.connection import _init_schema


def test_stock_menu_tables_are_created() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "kr_investor_flow",
        "kr_market_volume",
        "stock_fear_greed",
        "cboe_putcall",
        "index_shadow_judgments",
    } <= tables


def test_cboe_putcall_schema_matches_plan() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(cboe_putcall)").fetchall()
    }
    assert columns["date"]["pk"] == 1
    assert columns["date"]["notnull"] == 1
    assert columns["total_pc"]["type"] == "REAL"
    assert columns["equity_pc"]["type"] == "REAL"
    assert columns["index_pc"]["type"] == "REAL"
    assert columns["updated_at"]["type"] == "TEXT"
    assert columns["updated_at"]["notnull"] == 1


def test_index_shadow_judgments_schema_matches_plan() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(index_shadow_judgments)").fetchall()
    }
    assert columns["date"]["pk"] == 1
    assert columns["symbol"]["pk"] == 2
    assert columns["indicator"]["pk"] == 3
    assert columns["z"]["type"] == "REAL"
    assert columns["direction"]["type"] == "TEXT"
    assert columns["direction"]["notnull"] == 1
    assert columns["price"]["type"] == "REAL"
    assert columns["price"]["notnull"] == 1
    assert columns["price_after_7d"]["type"] == "REAL"
    assert columns["price_after_14d"]["type"] == "REAL"
    assert columns["price_after_30d"]["type"] == "REAL"
    assert columns["result_7d"]["type"] == "TEXT"
    assert columns["result_14d"]["type"] == "TEXT"
    assert columns["result_30d"]["type"] == "TEXT"
    assert columns["created_at"]["type"] == "TEXT"
    assert columns["created_at"]["notnull"] == 1


def test_kr_investor_flow_uses_market_date_primary_key() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(kr_investor_flow)").fetchall()
    }
    assert columns["date"]["pk"] == 1
    assert columns["market"]["pk"] == 2
    assert columns["foreign_net"]["type"] == "REAL"
    assert columns["institution_net"]["type"] == "REAL"
    assert columns["individual_net"]["type"] == "REAL"


def test_kr_market_volume_schema_matches_plan() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(kr_market_volume)").fetchall()
    }
    assert columns["date"]["pk"] == 1
    assert columns["kospi_value"]["type"] == "REAL"
    assert columns["kosdaq_value"]["type"] == "REAL"


def test_stock_fear_greed_schema_matches_plan() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(stock_fear_greed)").fetchall()
    }
    assert columns["date"]["pk"] == 1
    assert columns["value"]["type"] == "REAL"
    assert columns["value"]["notnull"] == 1
    assert columns["rating"]["type"] == "TEXT"
    assert columns["updated_at"]["type"] == "TEXT"
    assert columns["updated_at"]["notnull"] == 1


def test_daily_stock_tables_reject_null_dates() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _init_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO kr_market_volume (date, kospi_value, kosdaq_value) VALUES (NULL, 1.2, 0.8)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO stock_fear_greed (date, value, rating, updated_at) VALUES (NULL, 55, 'neutral', '2026-07-05T00:00:00+00:00')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at) VALUES (NULL, 0.79, 0.53, 0.97, '2026-07-05T00:00:00+00:00')"
        )
