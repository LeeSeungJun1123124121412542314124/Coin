"""반도체 외국인 순매도 시그널 자동화 테스트 — 파서·임계 판정·오버레이 폴백·멱등."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import sqlite3

import pytest

from dashboard.backend.db.connection import _init_schema


# 실제 m.stock.naver.com/api/stock/{code}/trend 응답 (2026-07-11 채집, 필드 축약)
NAVER_STOCK_TREND_JSON = [
    {
        "itemCode": "005930",
        "bizdate": "20260710",
        "foreignerPureBuyQuant": "+625,985",
        "foreignerHoldRatio": "46.58%",
        "organPureBuyQuant": "+2,313,745",
        "individualPureBuyQuant": "-2,851,466",
        "closePrice": "285,000",
        "accumulatedTradingVolume": "19,919,725",
    },
    {
        "itemCode": "005930",
        "bizdate": "20260708",
        "foreignerPureBuyQuant": "-3,015,093",
        "foreignerHoldRatio": "46.55%",
        "organPureBuyQuant": "+971,031",
        "individualPureBuyQuant": "+2,044,062",
        "closePrice": "277,500",
        "accumulatedTradingVolume": "33,525,758",
    },
    # 필드 누락 행 → 스킵되어야 함
    {"itemCode": "005930", "bizdate": "20260707"},
]


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _insert_flow_rows(
    conn: sqlite3.Connection,
    ticker: str,
    per_row_net: float,
    latest: date,
    count: int = 20,
) -> None:
    """ticker에 count개 행 삽입 — foreign_net은 행마다 per_row_net(억원)."""
    for i in range(count):
        row_date = latest - timedelta(days=i)
        conn.execute(
            """INSERT INTO kr_stock_investor_flow (date, ticker, foreign_net, institution_net)
               VALUES (?, ?, ?, ?)""",
            (row_date.isoformat(), ticker, per_row_net, 0.0),
        )


# ── T1-1: 종목별 trend JSON 파서 ──────────────────────────────────


def test_parse_stock_trend_json_converts_quantity_to_krw_amount() -> None:
    from dashboard.backend.collectors.naver_finance import parse_stock_trend_json

    records = parse_stock_trend_json(NAVER_STOCK_TREND_JSON)

    # 순매매량(주) × 종가(원) / 1e8 = 억원
    assert records == [
        {"date": "2026-07-10", "foreign_net": 1784.1, "institution_net": 6594.2},
        {"date": "2026-07-08", "foreign_net": -8366.9, "institution_net": 2694.6},
    ]


def test_parse_stock_trend_json_returns_empty_on_garbage() -> None:
    from dashboard.backend.collectors.naver_finance import parse_stock_trend_json

    assert parse_stock_trend_json([]) == []
    assert parse_stock_trend_json([{"foo": "bar"}]) == []


@pytest.mark.asyncio
async def test_fetch_stock_investor_trend_requests_page_size(monkeypatch) -> None:
    from dashboard.backend.collectors import naver_finance

    calls: list[tuple[str, dict]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list:
            return NAVER_STOCK_TREND_JSON

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict):
            calls.append((url, params))
            return FakeResponse()

    monkeypatch.setattr(naver_finance.httpx, "AsyncClient", FakeAsyncClient)

    records = await naver_finance.fetch_stock_investor_trend("005930", days=45)

    assert len(records) == 2
    assert calls[0][0] == "https://m.stock.naver.com/api/stock/005930/trend"
    assert calls[0][1] == {"pageSize": 30, "page": 1}  # 45 → 30으로 클램프


# ── T1-5: upsert 멱등 ─────────────────────────────────────────────


def test_upsert_kr_stock_investor_flow_is_idempotent(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_kr_stock

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    monkeypatch.setattr(collect_kr_stock, "get_db", fake_get_db)

    records = [
        {"date": "2026-07-10", "foreign_net": 1784.1, "institution_net": 6594.2},
        {"date": "2026-07-08", "foreign_net": -8366.9, "institution_net": 2694.6},
    ]
    collect_kr_stock.upsert_kr_stock_investor_flow("005930", records)
    collect_kr_stock.upsert_kr_stock_investor_flow("005930", records)

    rows = conn.execute(
        "SELECT date, ticker, foreign_net FROM kr_stock_investor_flow ORDER BY date"
    ).fetchall()
    assert len(rows) == 2
    assert rows[1]["foreign_net"] == 1784.1


@pytest.mark.asyncio
async def test_collect_job_includes_per_stock_flow(monkeypatch) -> None:
    from dashboard.backend.jobs import collect_kr_stock

    conn = _memory_conn()

    @contextmanager
    def fake_get_db():
        yield conn
        conn.commit()

    async def fake_fetch_investor_deal_trend(market: str, days: int = 30):
        return [{"date": "2026-07-10", "foreign_net": 1.0, "institution_net": 2.0, "individual_net": 3.0}]

    async def fake_fetch_market_volume(market: str, days: int = 30):
        return [{"date": "2026-07-10", "value": 12.3}]

    fetched: list[str] = []

    async def fake_fetch_stock_investor_trend(code: str, days: int = 30):
        assert days == 30
        fetched.append(code)
        return [{"date": "2026-07-10", "foreign_net": 100.0, "institution_net": 50.0}]

    monkeypatch.setattr(collect_kr_stock, "get_db", fake_get_db)
    monkeypatch.setattr(collect_kr_stock, "fetch_investor_deal_trend", fake_fetch_investor_deal_trend)
    monkeypatch.setattr(collect_kr_stock, "fetch_market_volume", fake_fetch_market_volume)
    monkeypatch.setattr(
        collect_kr_stock, "fetch_stock_investor_trend", fake_fetch_stock_investor_trend, raising=False
    )

    await collect_kr_stock.collect_kr_investor_flow()

    assert fetched == ["005930", "000660"]
    rows = conn.execute(
        "SELECT ticker FROM kr_stock_investor_flow ORDER BY ticker"
    ).fetchall()
    assert [row["ticker"] for row in rows] == ["000660", "005930"]


# ── T1-2: 누적·임계 판정 ──────────────────────────────────────────


def _overlay(conn, ticker: str, today: date):
    from dashboard.backend.db import connection
    from dashboard.backend.services.research_analyzer import _stock_flow_overlay

    @contextmanager
    def fake_get_db():
        yield conn

    import unittest.mock

    with unittest.mock.patch.object(connection, "get_db", fake_get_db):
        return _stock_flow_overlay(ticker, today=today)


def test_overlay_red_at_minus_3_trillion_boundary() -> None:
    conn = _memory_conn()
    today = date(2026, 7, 10)
    _insert_flow_rows(conn, "005930", per_row_net=-1500.0, latest=today)  # 누적 -3.0조

    result = _overlay(conn, "005930", today)

    assert result == {"status": "red", "label": "경보", "note": "최근 4주 누적 3.0조원 순매도 (자동)"}


def test_overlay_yellow_when_slightly_negative() -> None:
    conn = _memory_conn()
    today = date(2026, 7, 10)
    _insert_flow_rows(conn, "005930", per_row_net=-100.0, latest=today)  # 누적 -0.2조

    result = _overlay(conn, "005930", today)

    assert result["status"] == "yellow"
    assert result["label"] == "순매도 진행"
    assert result["note"] == "최근 4주 누적 0.2조원 순매도 (자동)"


def test_overlay_green_when_net_buying() -> None:
    conn = _memory_conn()
    today = date(2026, 7, 10)
    _insert_flow_rows(conn, "005930", per_row_net=500.0, latest=today)  # 누적 +1.0조

    result = _overlay(conn, "005930", today)

    assert result["status"] == "green"
    assert result["label"] == "아직 아님"
    assert result["note"] == "최근 4주 누적 1.0조원 순매수 (자동)"


# ── T1-3: 오버레이 적용·폴백 ──────────────────────────────────────


def test_overlay_returns_none_when_rows_insufficient() -> None:
    conn = _memory_conn()
    today = date(2026, 7, 10)
    _insert_flow_rows(conn, "005930", per_row_net=-1500.0, latest=today, count=19)

    assert _overlay(conn, "005930", today) is None


def test_overlay_returns_none_when_latest_row_stale() -> None:
    conn = _memory_conn()
    today = date(2026, 7, 10)
    _insert_flow_rows(conn, "005930", per_row_net=-1500.0, latest=today - timedelta(days=8))

    assert _overlay(conn, "005930", today) is None


@pytest.mark.asyncio
async def test_semiconductor_analysis_overlays_auto_signals_and_keeps_manual_fallback(monkeypatch) -> None:
    from dashboard.backend import cache
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    # 삼성만 20행 적재 (순매수) — 하이닉스는 데이터 없음 → 수동 폴백
    today = datetime.now(timezone.utc).date()
    _insert_flow_rows(conn, "005930", per_row_net=500.0, latest=today)

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)
    cache.delete_prefix("research_semiconductor")

    result = await research_analyzer._analyze_semiconductor_signals()
    cache.delete_prefix("research_semiconductor")

    signals = {s["id"]: s for sec in result["details"]["sections"] for s in sec["signals"]}
    # 삼성: DB 실측으로 덮어씀
    assert signals["samsung_foreign_selling"]["status"] == "green"
    assert signals["samsung_foreign_selling"]["note"] == "최근 4주 누적 1.0조원 순매수 (자동)"
    # 하이닉스: 데이터 없음 → 수동 상수값 유지
    manual = {
        s["id"]: s
        for sec in research_analyzer.SEMICONDUCTOR_SIGNALS
        for s in sec["signals"]
    }
    assert signals["hynix_foreign_selling"] == manual["hynix_foreign_selling"]
    # 원본 상수는 오염되지 않아야 함
    assert "(자동)" not in manual["samsung_foreign_selling"]["note"]
