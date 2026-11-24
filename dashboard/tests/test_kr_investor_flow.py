from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import sqlite3

import httpx
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.db.connection import _init_schema


def _mock_naver_index(monkeypatch, trading_days: list[str], trend: dict[str, tuple], bizdate_override: dict | None = None) -> list[httpx.Request]:
    """네이버 모바일 지수 API(price=거래일 목록, trend=날짜별 수급)를 실제 응답 형식으로 흉내낸다."""
    from dashboard.backend.collectors import naver_finance

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/price"):
            return httpx.Response(200, json=[{"localTradedAt": d, "closePrice": "5,000.00"} for d in trading_days])
        if request.url.path.endswith("/trend"):
            bizdate = request.url.params["bizdate"]
            personal, foreign, institutional = trend[bizdate]
            return httpx.Response(200, json={
                "bizdate": (bizdate_override or {}).get(bizdate, bizdate),
                "personalValue": personal,
                "foreignValue": foreign,
                "institutionalValue": institutional,
            })
        raise AssertionError(f"예상하지 못한 URL: {request.url}")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        naver_finance.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return requests


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


@pytest.mark.asyncio
async def test_fetch_investor_deal_trend_parses_mobile_trend_per_trading_day(monkeypatch) -> None:
    # 2026-09 실측 값 (운영 DB 기존 값과 일치 확인된 형식: 억원, 부호·콤마 문자열)
    from dashboard.backend.collectors import naver_finance

    requests = _mock_naver_index(
        monkeypatch,
        trading_days=["2026-09-16", "2026-09-15"],
        trend={"20260916": ("-12,061", "-16,726", "+12,251"), "20260915": ("+8,596", "-15,458", "-9,585")},
    )

    records = await naver_finance.fetch_investor_deal_trend("KOSPI", days=30)

    assert records == [
        {"date": "2026-09-16", "individual_net": -12061.0, "foreign_net": -16726.0, "institution_net": 12251.0},
        {"date": "2026-09-15", "individual_net": 8596.0, "foreign_net": -15458.0, "institution_net": -9585.0},
    ]
    assert all("/api/index/KOSPI/" in str(r.url) for r in requests)


@pytest.mark.asyncio
async def test_fetch_investor_deal_trend_requests_only_trading_days(monkeypatch) -> None:
    # 휴장일·주말 bizdate는 에러 대신 0/0/0을 돌려줘 가짜 행이 생긴다 → price 거래일만 요청해야 함
    from dashboard.backend.collectors import naver_finance

    requests = _mock_naver_index(
        monkeypatch,
        trading_days=["2026-10-12", "2026-10-08"],  # 10-09(한글날)·주말 없음
        trend={"20261012": ("+1", "+2", "+3"), "20261008": ("+4", "+5", "+6")},
    )

    await naver_finance.fetch_investor_deal_trend("KOSDAQ", days=30)

    asked = [r.url.params["bizdate"] for r in requests if r.url.path.endswith("/trend")]
    assert asked == ["20261012", "20261008"]


@pytest.mark.asyncio
async def test_fetch_investor_deal_trend_skips_mismatched_bizdate(monkeypatch) -> None:
    from dashboard.backend.collectors import naver_finance

    _mock_naver_index(
        monkeypatch,
        trading_days=["2026-11-17", "2026-11-16"],
        trend={"20261117": ("+1", "+2", "+3"), "20261116": ("+4", "+5", "+6")},
        bizdate_override={"20261116": "20261117"},  # 요청과 다른 날짜 응답
    )

    records = await naver_finance.fetch_investor_deal_trend("KOSPI", days=30)

    assert [r["date"] for r in records] == ["2026-11-17"]


@pytest.mark.asyncio
async def test_fetch_investor_deal_trend_caps_window_at_60(monkeypatch) -> None:
    from dashboard.backend.collectors import naver_finance

    requests = _mock_naver_index(monkeypatch, trading_days=[], trend={})

    await naver_finance.fetch_investor_deal_trend("KOSPI", days=90)

    price = next(r for r in requests if r.url.path.endswith("/price"))
    assert price.url.params["pageSize"] == "60"


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


@pytest.mark.parametrize("last_date, expected", [
    (None, 30),            # DB 비어있음 → 기존과 같은 30영업일
    ("2026-11-17", 30),    # 정상 운영 → 최근 30영업일 재수집(비확정 당일값 덮어쓰기)
    ("2026-09-17", 44),    # 2026-09-18~ 410 장애 공백 → 공백 평일 수만큼 백필
    ("2026-01-02", 60),    # 아주 오래된 공백 → 상한 60영업일
])
def test_collect_window_days_backfills_gap_within_30_to_60(last_date, expected) -> None:
    from dashboard.backend.jobs import collect_kr_stock

    assert collect_kr_stock._collect_window_days(last_date, date(2026, 11, 18)) == expected


@pytest.mark.asyncio
async def test_collect_kr_investor_flow_passes_gap_window_to_all_fetchers(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_kr_stock

    conn = _memory_conn()
    conn.execute(
        "INSERT INTO kr_investor_flow (date, market, foreign_net, institution_net, individual_net) VALUES ('2026-09-17', 'KOSPI', 0, 0, 0)"
    )

    @contextmanager
    def fake_get_db():
        yield conn

    seen: list[tuple[str, int]] = []

    async def fake_investor(market: str, days: int = 30):
        seen.append(("investor", days))
        return [{"date": "2026-11-18", "foreign_net": 1.0, "institution_net": 1.0, "individual_net": 1.0}]

    async def fake_volume(market: str, days: int = 30):
        seen.append(("volume", days))
        return [{"date": "2026-11-18", "value": 1.0}]

    monkeypatch.setattr(collect_kr_stock, "get_db", fake_get_db)
    monkeypatch.setattr(collect_kr_stock, "_kst_today", lambda: date(2026, 11, 18))
    monkeypatch.setattr(collect_kr_stock, "fetch_investor_deal_trend", fake_investor)
    monkeypatch.setattr(collect_kr_stock, "fetch_market_volume", fake_volume)

    await collect_kr_stock.collect_kr_investor_flow.__wrapped__()

    assert {days for _, days in seen} == {44}
    assert {kind for kind, _ in seen} == {"investor", "volume"}


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
