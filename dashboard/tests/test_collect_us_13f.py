from __future__ import annotations

from contextlib import contextmanager
import sqlite3

from dashboard.backend.db.connection import _init_schema


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


@contextmanager
def _fake_db(conn):
    yield conn


def test_replace_holdings_replaces_same_cik_and_quarter(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_us_13f

    conn = _memory_conn()
    monkeypatch.setattr(collect_us_13f, "get_db", lambda: _fake_db(conn))
    original = [{"seq": 0, "ticker": "AAPL", "issuer_name": "APPLE INC", "shares": 10, "value_usd": 100, "put_call": None}]
    amended = [{"seq": 2, "ticker": "MSFT", "issuer_name": "MICROSOFT CORP", "shares": 20, "value_usd": 200, "put_call": "Call"}]

    collect_us_13f.replace_13f_holdings("original", "Berkshire Hathaway", 1067983, "2026-06-30", original)
    collect_us_13f.replace_13f_holdings("amended", "Berkshire Hathaway", 1067983, "2026-06-30", amended)

    rows = conn.execute("SELECT accession_no, seq, ticker, put_call FROM us_13f_holdings").fetchall()
    assert [tuple(row) for row in rows] == [("amended", 2, "MSFT", "Call")]


def test_filing_metadata_is_idempotent_and_tracks_zero_matches(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_us_13f

    conn = _memory_conn()
    monkeypatch.setattr(collect_us_13f, "get_db", lambda: _fake_db(conn))

    collect_us_13f.upsert_13f_filing("zero-match", 1067983, "Berkshire Hathaway", "2026-08-14", "2026-06-30")
    collect_us_13f.upsert_13f_filing("zero-match", 1067983, "Berkshire Hathaway", "2026-08-14", "2026-06-30")

    assert collect_us_13f.known_13f_accessions() == {"zero-match"}
    assert conn.execute("SELECT COUNT(*) FROM us_13f_filings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM us_13f_holdings").fetchone()[0] == 0
