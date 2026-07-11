from __future__ import annotations

from contextlib import contextmanager
import sqlite3

import pytest

from dashboard.backend.db.connection import _init_schema


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _seed_flow(conn: sqlite3.Connection, days: int, foreign_per_day: float, institution_per_day: float) -> None:
    rows = [
        (f"2026-06-{d:02d}" if d <= 30 else f"2026-07-{d - 30:02d}", "KOSPI", foreign_per_day, institution_per_day, 0.0)
        for d in range(1, days + 1)
    ]
    conn.executemany(
        """INSERT INTO kr_investor_flow (date, market, foreign_net, institution_net, individual_net)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )


def _seed_volume(conn: sqlite3.Connection, first15_total: float, last5_total: float) -> None:
    # 20영업일: 앞 15일은 first15_total, 뒤 5일은 last5_total (KOSPI+KOSDAQ 합산 기준, 반씩 배분)
    rows = []
    for d in range(1, 21):
        total = first15_total if d <= 15 else last5_total
        date = f"2026-06-{d:02d}"
        rows.append((date, total / 2, total / 2))
    conn.executemany(
        "INSERT INTO kr_market_volume (date, kospi_value, kosdaq_value) VALUES (?, ?, ?)",
        rows,
    )


@contextmanager
def _fake_db(conn):
    yield conn


@pytest.mark.asyncio
async def test_kr_stock_flow_max_risk_at_band_edges(monkeypatch) -> None:
    """외국인+기관 20일 누적 -5조원 + 거래대금 비율 1.5 → 100점 critical."""
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    _seed_flow(conn, days=20, foreign_per_day=-1500.0, institution_per_day=-1000.0)  # 합계 -50,000억
    _seed_volume(conn, first15_total=10.0, last5_total=30.0)  # 5일평균/20일평균 = 2.0 (밴드 상단 초과 → 클램프 100)

    monkeypatch.setattr(connection, "get_db", lambda: _fake_db(conn))

    result = await research_analyzer._analyze_kr_stock_flow()

    assert result["key"] == "kr_stock_flow"
    assert result["name"] == "주식수급"
    assert result["score"] == 100
    assert result["level"] == "critical"
    assert result["details"]["flow_total_20d"] == -50000.0
    assert result["details"]["foreign_20d"] == -30000.0
    assert result["details"]["institution_20d"] == -20000.0
    assert result["details"]["volume_ratio"] == 2.0
    assert result["details"]["component_scores"] == {"flow": 100.0, "volume": 100.0}


@pytest.mark.asyncio
async def test_kr_stock_flow_min_risk_at_opposite_band_edges(monkeypatch) -> None:
    """외국인+기관 20일 누적 +5조원 + 거래대금 비율 0.7 미만 → 0점 bullish."""
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    _seed_flow(conn, days=20, foreign_per_day=1500.0, institution_per_day=1000.0)  # 합계 +50,000억
    _seed_volume(conn, first15_total=10.0, last5_total=5.0)  # 비율 0.57 (밴드 하단 미만 → 클램프 0)

    monkeypatch.setattr(connection, "get_db", lambda: _fake_db(conn))

    result = await research_analyzer._analyze_kr_stock_flow()

    assert result["score"] == 0
    assert result["level"] == "bullish"
    assert result["details"]["component_scores"] == {"flow": 0.0, "volume": 0.0}


@pytest.mark.asyncio
async def test_kr_stock_flow_falls_back_when_samples_insufficient(monkeypatch) -> None:
    """20영업일 미만 적재 시 '데이터 적재 중' 폴백 — 적재가 차면 자동으로 살아난다."""
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    _seed_flow(conn, days=10, foreign_per_day=-100.0, institution_per_day=0.0)
    _seed_volume(conn, first15_total=10.0, last5_total=10.0)

    monkeypatch.setattr(connection, "get_db", lambda: _fake_db(conn))

    result = await research_analyzer._analyze_kr_stock_flow()

    assert result["key"] == "kr_stock_flow"
    assert result["name"] == "주식수급"
    assert result["score"] == 0
    assert result["level"] == "neutral"
    assert "10/20" in result["summary"]
    assert result["details"] == {}


@pytest.mark.asyncio
async def test_analyze_all_appends_kr_stock_flow_as_tenth_category(monkeypatch) -> None:
    from dashboard.backend.services import research_analyzer

    async def fake_category(key: str) -> dict:
        return {
            "key": key,
            "name": key,
            "level": "neutral",
            "score": 0,
            "title": key,
            "summary": key,
            "details": {},
            "updated_at": "2026-07-12T00:00:00+00:00",
        }

    for name, key in [
        ("_analyze_macro", "macro"),
        ("_analyze_onchain", "onchain"),
        ("_analyze_derivatives", "derivatives"),
        ("_analyze_altcoin", "altcoin"),
        ("_analyze_technical", "technical"),
        ("_analyze_market", "market"),
        ("_analyze_whale", "whale"),
        ("_analyze_semiconductor_signals", "semiconductor_signals"),
        ("_analyze_stock_sentiment", "stock_sentiment"),
        ("_analyze_kr_stock_flow", "kr_stock_flow"),
    ]:
        async def fake(key=key):
            return await fake_category(key)

        monkeypatch.setattr(research_analyzer, name, fake, raising=False)

    result = await research_analyzer.analyze_all()

    keys = [category["key"] for category in result["categories"]]
    assert keys[8] == "stock_sentiment"
    assert keys[9] == "kr_stock_flow"
    names = [category["name"] for category in result["categories"]]
    assert len(names) == 10
