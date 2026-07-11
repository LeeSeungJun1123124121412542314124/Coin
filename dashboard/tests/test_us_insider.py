from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from dashboard.backend.db.connection import _init_schema


FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer>
        <issuerCik>0001045810</issuerCik>
        <issuerName>NVIDIA CORP</issuerName>
        <issuerTradingSymbol>NVDA</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001234567</rptOwnerCik>
            <rptOwnerName>HUANG JEN HSUN</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>1</isDirector>
            <isOfficer>1</isOfficer>
            <officerTitle>President and CEO</officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-08</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>1000</value></transactionShares>
                <transactionPricePerShare><value>150.5</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-09</value></transactionDate>
            <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>200</value></transactionShares>
                <transactionPricePerShare><value>149.0</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-09</value></transactionDate>
            <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>5000</value></transactionShares>
                <transactionPricePerShare><value>0</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_form4_extracts_owner_and_open_market_transactions_only() -> None:
    from dashboard.backend.collectors.edgar import parse_form4_xml

    parsed = parse_form4_xml(FORM4_XML)

    assert parsed["insider_name"] == "HUANG JEN HSUN"
    assert parsed["insider_title"] == "President and CEO"
    # 코드 P/S만 — 수여(A)는 제외
    assert parsed["transactions"] == [
        {"date": "2026-07-08", "code": "S", "shares": 1000.0, "price": 150.5, "value": -150500.0},
        {"date": "2026-07-09", "code": "P", "shares": 200.0, "price": 149.0, "value": 29800.0},
    ]


def test_parse_form4_falls_back_to_director_title() -> None:
    from dashboard.backend.collectors.edgar import parse_form4_xml

    xml = FORM4_XML.replace("<officerTitle>President and CEO</officerTitle>", "")
    parsed = parse_form4_xml(xml)
    assert parsed["insider_title"] == "Director"


def test_normalize_primary_document_strips_xsl_prefix() -> None:
    from dashboard.backend.collectors.edgar import normalize_primary_document

    assert normalize_primary_document("xslF345X05/wk-form4_168.xml") == "wk-form4_168.xml"
    assert normalize_primary_document("form4.xml") == "form4.xml"


def test_parse_submissions_filters_form4_within_window() -> None:
    from dashboard.backend.collectors.edgar import parse_submissions

    payload = {
        "filings": {
            "recent": {
                "form": ["4", "10-K", "4", "4/A", "4"],
                "accessionNumber": ["0001-26-000001", "0001-26-000002", "0001-26-000003", "0001-26-000004", "0001-26-000005"],
                "filingDate": ["2026-07-10", "2026-07-09", "2026-07-01", "2026-06-30", "2026-01-02"],
                "primaryDocument": ["a.xml", "b.htm", "xslF345X05/c.xml", "d.xml", "e.xml"],
            }
        }
    }

    filings = parse_submissions(payload, since="2026-04-13")

    assert filings == [
        {"accession_no": "0001-26-000001", "filed_at": "2026-07-10", "primary_document": "a.xml"},
        {"accession_no": "0001-26-000003", "filed_at": "2026-07-01", "primary_document": "xslF345X05/c.xml"},
    ]


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


@contextmanager
def _fake_db(conn):
    yield conn


def test_upsert_us_insider_trades_is_idempotent(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_us_insider

    conn = _memory_conn()
    monkeypatch.setattr(collect_us_insider, "get_db", lambda: _fake_db(conn))

    parsed = {
        "insider_name": "HUANG JEN HSUN",
        "insider_title": "President and CEO",
        "transactions": [
            {"date": "2026-07-08", "code": "S", "shares": 1000.0, "price": 150.5, "value": -150500.0},
            {"date": "2026-07-09", "code": "P", "shares": 200.0, "price": 149.0, "value": 29800.0},
        ],
    }

    inserted = collect_us_insider.upsert_us_insider_trades("NVDA", "0001-26-000001", "2026-07-10", parsed)
    assert inserted == 2
    collect_us_insider.upsert_us_insider_trades("NVDA", "0001-26-000001", "2026-07-10", parsed)

    rows = conn.execute("SELECT COUNT(*) AS n FROM us_insider_trades").fetchone()
    assert rows["n"] == 2


@pytest.mark.asyncio
async def test_collect_us_insider_trades_skips_known_accessions(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_us_insider

    conn = _memory_conn()
    monkeypatch.setattr(collect_us_insider, "get_db", lambda: _fake_db(conn))
    monkeypatch.setattr(collect_us_insider, "_REQUEST_DELAY_S", 0.0)
    # 슬롯을 단일 종목으로 고정
    conn.execute("DELETE FROM stock_slots WHERE market='us'")
    conn.execute(
        "INSERT INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES ('us', 1, 'NVDA', '엔비디아', 'NASDAQ:NVDA')"
    )

    async def fake_cik_map():
        return {"NVDA": 1045810}

    filings = [
        {"accession_no": "0001-26-000001", "filed_at": "2026-07-10", "primary_document": "a.xml"},
        {"accession_no": "0001-26-000002", "filed_at": "2026-07-09", "primary_document": "b.xml"},
    ]

    async def fake_recent(cik, since):
        assert cik == 1045810
        return filings

    fetched: list[str] = []

    async def fake_form4(cik, accession_no, primary_document):
        fetched.append(accession_no)
        return {
            "insider_name": "X",
            "insider_title": None,
            "transactions": [
                {"date": "2026-07-08", "code": "P", "shares": 1.0, "price": 10.0, "value": 10.0},
            ],
        }

    monkeypatch.setattr(collect_us_insider, "fetch_cik_map", fake_cik_map)
    monkeypatch.setattr(collect_us_insider, "fetch_recent_form4_filings", fake_recent)
    monkeypatch.setattr(collect_us_insider, "fetch_form4", fake_form4)

    await collect_us_insider.collect_us_insider_trades()
    assert sorted(fetched) == ["0001-26-000001", "0001-26-000002"]

    # 2회차: 이미 저장된 accession은 다시 가져오지 않는다
    fetched.clear()
    await collect_us_insider.collect_us_insider_trades()
    assert fetched == []


def test_us_insider_trades_api_returns_slot_summaries_and_trades(monkeypatch) -> None:
    from dashboard.backend.api import whale_routes

    conn = _memory_conn()
    monkeypatch.setattr(whale_routes, "get_db", lambda: _fake_db(conn))

    conn.execute("DELETE FROM stock_slots WHERE market='us'")
    conn.executemany(
        "INSERT INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES ('us', ?, ?, ?, NULL)",
        [(1, "NVDA", "엔비디아"), (2, "AAPL", "애플")],
    )

    recent = (date.today() - timedelta(days=5)).isoformat()
    old = (date.today() - timedelta(days=120)).isoformat()
    conn.executemany(
        """INSERT INTO us_insider_trades
           (accession_no, seq, ticker, filed_at, transaction_date, insider_name, insider_title, code, shares, price, value)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("acc-1", 0, "NVDA", recent, recent, "HUANG JEN HSUN", "CEO", "S", 1000.0, 150.0, -150000.0),
            ("acc-2", 0, "NVDA", recent, recent, "SOMEONE", "CFO", "P", 100.0, 150.0, 15000.0),
            ("acc-3", 0, "AAPL", recent, recent, "COOK TIM", "CEO", "P", 200.0, 200.0, 40000.0),
            # 90일 밖 거래는 요약·목록 모두 제외
            ("acc-4", 0, "NVDA", old, old, "OLD GUY", None, "S", 10.0, 100.0, -1000.0),
        ],
    )

    app = FastAPI()
    app.include_router(whale_routes.router, prefix="/api")
    client = TestClient(app)

    resp = client.get("/api/whale/us-insider-trades")
    assert resp.status_code == 200
    body = resp.json()

    assert body["summaries"] == [
        {"ticker": "NVDA", "name": "엔비디아", "buy_value": 15000.0, "sell_value": -150000.0, "net_value": -135000.0, "trade_count": 2},
        {"ticker": "AAPL", "name": "애플", "buy_value": 40000.0, "sell_value": 0.0, "net_value": 40000.0, "trade_count": 1},
    ]
    assert len(body["trades"]) == 3
    assert all(trade["transaction_date"] == recent for trade in body["trades"])
    assert {trade["ticker"] for trade in body["trades"]} == {"NVDA", "AAPL"}
