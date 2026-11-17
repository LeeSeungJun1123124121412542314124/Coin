from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from unittest.mock import Mock

import pytest

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


@pytest.mark.asyncio
async def test_collect_us_13f_end_to_end_and_second_run_skips_download(monkeypatch) -> None:
    from dashboard.backend.collectors import edgar
    from dashboard.backend.jobs import collect_us_13f

    conn = _memory_conn()
    monkeypatch.setattr(collect_us_13f, "get_db", lambda: _fake_db(conn))
    monkeypatch.setattr(collect_us_13f, "_INSTITUTIONS", [("Berkshire Hathaway", 1067983)])
    monkeypatch.setattr(collect_us_13f, "_REQUEST_DELAY_S", 0.0)
    conn.execute("DELETE FROM stock_slots WHERE market='us'")
    conn.execute(
        "INSERT INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES ('us', 1, 'AAPL', '애플', 'NASDAQ:AAPL')"
    )

    infotable_downloads = 0

    class FakeResponse:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            nonlocal infotable_downloads
            if url.endswith("company_tickers.json"):
                return FakeResponse({"0": {"ticker": "AAPL", "title": "APPLE INC"}})
            if "submissions" in url:
                return FakeResponse({
                    "name": "BERKSHIRE HATHAWAY INC",
                    "filings": {"recent": {
                        "form": ["13F-HR"], "accessionNumber": ["acc-1"],
                        "filingDate": ["2026-08-14"], "primaryDocument": ["primary.xml"],
                        "reportDate": ["2026-06-30"],
                    }},
                })
            if url.endswith("index.json"):
                return FakeResponse({"directory": {"item": [{"name": "infotable.xml", "type": "INFORMATION TABLE"}]}})
            if url.endswith("infotable.xml"):
                infotable_downloads += 1
                return FakeResponse(text="""<informationTable><infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip><value>123</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt></infoTable><infoTable><nameOfIssuer>NOT IN SLOT</nameOfIssuer><cusip>000</cusip><value>9</value><shrsOrPrnAmt><sshPrnamt>1</sshPrnamt></shrsOrPrnAmt></infoTable></informationTable>""")
            raise AssertionError(f"예상하지 못한 URL: {url}")

    monkeypatch.setattr(edgar.httpx, "AsyncClient", FakeClient)

    await collect_us_13f.collect_us_13f_holdings()
    await collect_us_13f.collect_us_13f_holdings()

    rows = conn.execute("SELECT seq, ticker, value_usd FROM us_13f_holdings").fetchall()
    assert [tuple(row) for row in rows] == [(0, "AAPL", 123.0)]
    assert infotable_downloads == 1
    assert collect_us_13f.known_13f_accessions() == {"acc-1"}


@pytest.mark.asyncio
async def test_one_failed_filing_does_not_block_other_institutions(monkeypatch) -> None:
    # 2026-11-16 운영: 첫 기관(Berkshire) 판별 실패 하나로 잡 전체가 중단돼 4개 기관 모두 0건
    from dashboard.backend.collectors import edgar
    from dashboard.backend.jobs import collect_us_13f

    conn = _memory_conn()
    monkeypatch.setattr(collect_us_13f, "get_db", lambda: _fake_db(conn))
    monkeypatch.setattr(collect_us_13f, "_INSTITUTIONS", [
        ("Berkshire Hathaway", 1067983),
        ("Bridgewater Associates", 1350694),
    ])
    monkeypatch.setattr(collect_us_13f, "_REQUEST_DELAY_S", 0.0)
    conn.execute("DELETE FROM stock_slots WHERE market='us'")
    conn.execute(
        "INSERT INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES ('us', 1, 'AAPL', '애플', 'NASDAQ:AAPL')"
    )

    names = {1067983: "BERKSHIRE HATHAWAY INC", 1350694: "Bridgewater Associates, LP"}

    class FakeResponse:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            if url.endswith("company_tickers.json"):
                return FakeResponse({"0": {"ticker": "AAPL", "title": "APPLE INC"}})
            cik = next(c for c in names if f"{c:010d}" in url or f"/{c}/" in url)
            if "submissions" in url:
                return FakeResponse({
                    "name": names[cik],
                    "filings": {"recent": {
                        "form": ["13F-HR"], "accessionNumber": [f"acc-{cik}"],
                        "filingDate": ["2026-11-16"], "primaryDocument": ["xslForm13F_X02/primary_doc.xml"],
                        "reportDate": ["2026-09-30"],
                    }},
                })
            if url.endswith("index.json"):
                # Berkshire: 정보테이블 후보 XML 없음 → 판별 실패
                xmls = ["primary_doc.xml"] if cik == 1067983 else ["infotable.xml", "primary_doc.xml"]
                return FakeResponse({"directory": {"item": [{"name": n, "type": "text.gif"} for n in xmls]}})
            if url.endswith("infotable.xml"):
                return FakeResponse(text="""<informationTable><infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip><value>123</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt></infoTable></informationTable>""")
            raise AssertionError(f"예상하지 못한 URL: {url}")

    monkeypatch.setattr(edgar.httpx, "AsyncClient", FakeClient)

    # 재시도 데코레이터의 대기를 피해 원본 함수 호출
    with pytest.raises(RuntimeError, match="acc-1067983"):
        await collect_us_13f.collect_us_13f_holdings.__wrapped__()

    rows = conn.execute("SELECT institution, ticker FROM us_13f_holdings").fetchall()
    assert [tuple(row) for row in rows] == [("Bridgewater Associates", "AAPL")]
    assert collect_us_13f.known_13f_accessions() == {"acc-1350694"}  # 실패 공시는 다음 실행에 재시도


def test_registers_us_13f_schedule_on_monday_at_0920_utc() -> None:
    from dashboard.backend.main import _register_jobs

    scheduler = Mock()
    _register_jobs(scheduler, Mock(), Mock())

    call = next(call for call in scheduler.add_job.call_args_list if call.kwargs.get("id") == "collect_us_13f")
    trigger = call.args[1]
    assert str(trigger.fields[4]) == "mon"
    assert str(trigger.fields[5]) == "9"
    assert str(trigger.fields[6]) == "20"
    assert str(trigger.timezone) == "UTC"
