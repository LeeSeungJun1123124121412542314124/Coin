from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import sqlite3

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.db.connection import _init_schema


NAVER_INVESTOR_HTML = """
<html>
  <body>
    <table>
      <caption>일자별 순매수</caption>
      <tr>
        <th>날짜</th><th>개인</th><th>외국인</th><th>기관계</th>
        <th>금융투자</th><th>보험</th><th>투신(사모)</th><th>은행</th>
        <th>기타금융기관</th><th>연기금등</th><th>기타법인</th>
      </tr>
      <tr>
        <td>26.07.03</td><td>12,345</td><td>-22,942</td><td>10,597</td>
        <td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td>
      </tr>
      <tr>
        <td>26.07.02</td><td>-1,000</td><td>2,000</td><td>-3,000</td>
        <td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td>
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


def test_parse_naver_investor_flow_html_extracts_core_columns() -> None:
    from dashboard.backend.collectors.naver_finance import parse_investor_flow_html

    records = parse_investor_flow_html(NAVER_INVESTOR_HTML)

    assert records == [
        {
            "date": "2026-07-03",
            "individual_net": 12345.0,
            "foreign_net": -22942.0,
            "institution_net": 10597.0,
        },
        {
            "date": "2026-07-02",
            "individual_net": -1000.0,
            "foreign_net": 2000.0,
            "institution_net": -3000.0,
        },
    ]


@pytest.mark.asyncio
async def test_fetch_investor_deal_trend_caps_results_at_30(monkeypatch) -> None:
    from dashboard.backend.collectors import naver_finance

    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, page: int) -> None:
            self.page = page
            self.content = self._html().encode("euc-kr")

        def _html(self) -> str:
            base = date(2026, 7, 3) - timedelta(days=(self.page - 1) * 10)
            rows = []
            for offset in range(10):
                row_date = base - timedelta(days=offset)
                rows.append(
                    "<tr>"
                    f"<td>{row_date.strftime('%y.%m.%d')}</td>"
                    f"<td>{offset}</td><td>{offset + 1}</td><td>{offset + 2}</td>"
                    "<td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td>"
                    "</tr>"
                )
            return "<table><caption>일자별 순매수</caption>" + "".join(rows) + "</table>"

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict):
            calls.append(params)
            return FakeResponse(params["page"])

    monkeypatch.setattr(naver_finance.httpx, "AsyncClient", FakeAsyncClient)

    records = await naver_finance.fetch_investor_deal_trend("KOSDAQ", days=45)

    assert len(records) == 30
    assert [call["page"] for call in calls] == [1, 2, 3]
    assert {call["sosok"] for call in calls} == {"02"}


def test_kr_investor_flow_api_returns_sorted_records_and_stale_flag(monkeypatch) -> None:
    from dashboard.backend.api import whale_routes

    conn = _memory_conn()
    conn.executemany(
        """INSERT INTO kr_investor_flow
           (date, market, foreign_net, institution_net, individual_net)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("2026-07-02", "KOSPI", 2000, -3000, -1000),
            ("2026-07-03", "KOSPI", -22942, 10597, 12345),
            ("2026-07-03", "KOSDAQ", 100, 200, -300),
        ],
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(whale_routes, "get_db", fake_get_db)
    monkeypatch.setattr(whale_routes, "_kst_today", lambda: date(2026, 7, 5))

    app = FastAPI()
    app.include_router(whale_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/whale/kr-investor-flow?market=KOSPI&days=2")

    assert response.status_code == 200
    assert response.json() == {
        "market": "KOSPI",
        "stale": False,
        "records": [
            {
                "date": "2026-07-02",
                "foreign_net": 2000.0,
                "institution_net": -3000.0,
                "individual_net": -1000.0,
            },
            {
                "date": "2026-07-03",
                "foreign_net": -22942.0,
                "institution_net": 10597.0,
                "individual_net": 12345.0,
            },
        ],
    }


def test_kr_investor_flow_api_marks_old_data_stale(monkeypatch) -> None:
    from dashboard.backend.api import whale_routes

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO kr_investor_flow
           (date, market, foreign_net, institution_net, individual_net)
           VALUES (?, ?, ?, ?, ?)""",
        ("2026-06-20", "KOSPI", 1, 2, 3),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(whale_routes, "get_db", fake_get_db)
    monkeypatch.setattr(whale_routes, "_kst_today", lambda: date(2026, 7, 5))

    app = FastAPI()
    app.include_router(whale_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/whale/kr-investor-flow?market=KOSPI")

    assert response.status_code == 200
    assert response.json()["stale"] is True


def test_kr_investor_flow_api_rejects_unknown_market() -> None:
    from dashboard.backend.api import whale_routes

    app = FastAPI()
    app.include_router(whale_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/whale/kr-investor-flow?market=NASDAQ")

    assert 400 <= response.status_code < 500


def test_kr_investor_flow_api_limits_days_to_30() -> None:
    from dashboard.backend.api import whale_routes

    app = FastAPI()
    app.include_router(whale_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/whale/kr-investor-flow?market=KOSPI&days=31")

    assert 400 <= response.status_code < 500


@pytest.mark.asyncio
async def test_collect_kr_investor_flow_upserts_both_markets_and_market_volume(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_kr_stock

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_investor_deal_trend(market: str, days: int = 30):
        assert days == 30
        return [{
            "date": "2026-07-03",
            "foreign_net": 1.0 if market == "KOSPI" else 10.0,
            "institution_net": 2.0 if market == "KOSPI" else 20.0,
            "individual_net": 3.0 if market == "KOSPI" else 30.0,
        }]

    async def fake_fetch_market_volume(market: str, days: int = 30):
        assert days == 30
        return [{
            "date": "2026-07-03",
            "value": 12.3 if market == "KOSPI" else 5.2,
        }]

    monkeypatch.setattr(collect_kr_stock, "get_db", fake_get_db)
    monkeypatch.setattr(collect_kr_stock, "fetch_investor_deal_trend", fake_fetch_investor_deal_trend)
    monkeypatch.setattr(collect_kr_stock, "fetch_market_volume", fake_fetch_market_volume, raising=False)

    await collect_kr_stock.collect_kr_investor_flow()

    rows = conn.execute(
        """SELECT date, market, foreign_net, institution_net, individual_net
           FROM kr_investor_flow
           ORDER BY market"""
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "date": "2026-07-03",
            "market": "KOSDAQ",
            "foreign_net": 10.0,
            "institution_net": 20.0,
            "individual_net": 30.0,
        },
        {
            "date": "2026-07-03",
            "market": "KOSPI",
            "foreign_net": 1.0,
            "institution_net": 2.0,
            "individual_net": 3.0,
        },
    ]
    volume_rows = conn.execute(
        """SELECT date, kospi_value, kosdaq_value
           FROM kr_market_volume"""
    ).fetchall()
    assert [dict(row) for row in volume_rows] == [{
        "date": "2026-07-03",
        "kospi_value": 12.3,
        "kosdaq_value": 5.2,
    }]


@pytest.mark.asyncio
async def test_collect_kr_investor_flow_raises_when_market_returns_no_records(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_kr_stock

    async def fake_fetch_investor_deal_trend(market: str, days: int = 30):
        if market == "KOSPI":
            return []
        return [{
            "date": "2026-07-03",
            "foreign_net": 1.0,
            "institution_net": 2.0,
            "individual_net": 3.0,
        }]

    monkeypatch.setattr(collect_kr_stock, "fetch_investor_deal_trend", fake_fetch_investor_deal_trend)
    monkeypatch.setattr(
        collect_kr_stock,
        "fetch_market_volume",
        lambda market, days=30: [],
        raising=False,
    )

    with pytest.raises(RuntimeError, match="KOSPI"):
        await collect_kr_stock.collect_kr_investor_flow()


def test_kr_investor_flow_job_is_registered_at_utc_0830() -> None:
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")

    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())

    job = scheduler.get_job("collect_kr_investor_flow")
    assert job is not None
    assert job.trigger.fields[5].expressions[0].first == 8
    assert job.trigger.fields[6].expressions[0].first == 30
    assert job.trigger.timezone.utcoffset(None).total_seconds() == 0
