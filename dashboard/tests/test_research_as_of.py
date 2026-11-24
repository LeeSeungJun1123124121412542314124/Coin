"""늦게 나오는 데이터에는 기준일을 붙인다 — 값이 며칠째 같아 보여도 언제 값인지 알 수 있게."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import sqlite3

import pytest

from dashboard.backend.db.connection import _init_schema


@pytest.mark.asyncio
async def test_onchain_summary_starts_with_data_date(monkeypatch) -> None:
    """Coin Metrics는 하루치 값을 이틀쯤 늦게 준다 — 요약 앞에 그 날짜를 붙인다."""
    from app.data import data_collector
    from dashboard.backend.services import research_analyzer

    async def fake_fetch(self, coin: str = "btc"):
        return {
            "exchange_inflow": 14441.8,
            "exchange_outflow": 13517.4,
            "whale_transaction_volume": 27.96,
            "dormant_whale_activated": False,
            "mvrv": 1.9,
            "as_of": "2026-11-22",
        }

    monkeypatch.setattr(data_collector.DataCollector, "fetch_onchain_data", fake_fetch)

    result = await research_analyzer._analyze_onchain.__wrapped__()

    assert result["summary"].startswith("11-22 기준 · 유입/유출 비율 ")
    assert result["details"]["as_of"] == "2026-11-22"


@pytest.mark.asyncio
async def test_onchain_summary_without_date_keeps_old_format(monkeypatch) -> None:
    from app.data import data_collector
    from dashboard.backend.services import research_analyzer

    async def fake_fetch(self, coin: str = "btc"):
        return {
            "exchange_inflow": 100.0,
            "exchange_outflow": 100.0,
            "whale_transaction_volume": 0.2,
            "dormant_whale_activated": False,
            "mvrv": None,
        }

    monkeypatch.setattr(data_collector.DataCollector, "fetch_onchain_data", fake_fetch)

    result = await research_analyzer._analyze_onchain.__wrapped__()

    assert result["summary"].startswith("유입/유출 비율 ")
    assert result["details"]["as_of"] is None


@pytest.mark.asyncio
async def test_fetch_onchain_data_returns_data_date(monkeypatch) -> None:
    import httpx

    from app.data import data_collector

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{
            "asset": "btc",
            "time": "2026-11-22T00:00:00.000000000Z",
            "FlowInExNtv": "14441.8",
            "FlowOutExNtv": "13517.4",
            "CapMVRVCur": "1.9",
        }]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        data_collector.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )

    raw = await data_collector.DataCollector().fetch_onchain_data("btc")

    assert raw["as_of"] == "2026-11-22"
    assert raw["exchange_inflow"] == 14441.8


@pytest.mark.asyncio
async def test_stock_sentiment_summary_shows_each_data_date(monkeypatch) -> None:
    """풋콜 비율은 하루 늦게 나온다 — 공포탐욕과 날짜가 다를 수 있어 각각 붙인다."""
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    conn.execute(
        "INSERT INTO stock_fear_greed (date, value, rating, updated_at) VALUES (?, ?, ?, ?)",
        ("2026-11-23", 17.0, "extreme fear", "2026-11-23T23:26:15+00:00"),
    )
    conn.execute(
        "INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("2026-11-20", 1.13, 0.77, 1.27, "2026-11-23T22:30:04+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)

    result = await research_analyzer._analyze_stock_sentiment()

    assert result["summary"] == "F&G 17.0 (11-23) | Put/Call 0.77 (11-20)"


@pytest.mark.asyncio
async def test_macro_summary_shows_weekly_and_monthly_data_dates(monkeypatch) -> None:
    """TGA는 주간, M2는 월간이라 최신 값이 오래돼 보인다 — 언제 값인지 붙인다."""
    from dashboard.backend.collectors import fred, treasury, yahoo_finance
    from dashboard.backend.services import research_analyzer

    last_week = date(2026, 11, 18)
    tga = [
        {"date": (last_week - timedelta(weeks=59 - i)).isoformat(), "value": 900000.0 + i}
        for i in range(60)
    ]
    m2 = [
        {"date": date(2025 + (7 + i) // 12, (7 + i) % 12 + 1, 1).isoformat(), "value": 22000.0 + i * 10}
        for i in range(14)
    ]  # 2025-08 ~ 2026-09
    assert m2[-1]["date"] == "2026-09-01"

    async def fake_tga():
        return tga

    async def fake_m2():
        return m2

    async def fake_empty(*args, **kwargs):
        return []

    monkeypatch.setattr(fred, "fetch_tga", fake_tga)
    monkeypatch.setattr(fred, "fetch_m2", fake_m2)
    monkeypatch.setattr(fred, "fetch_soma", fake_empty)
    monkeypatch.setattr(yahoo_finance, "fetch_us_market", fake_empty)
    monkeypatch.setattr(treasury, "fetch_upcoming_auctions", fake_empty)

    result = await research_analyzer._analyze_macro.__wrapped__()
    parts = result["summary"].split(" | ")

    tga_part = next(p for p in parts if p.startswith("TGA "))
    m2_part = next(p for p in parts if p.startswith("M2 "))
    assert "(11-18 기준 · YoY " in tga_part
    assert "(9월 기준" in m2_part
