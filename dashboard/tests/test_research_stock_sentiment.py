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


@pytest.mark.asyncio
async def test_analyze_stock_sentiment_uses_latest_fear_greed_and_putcall(monkeypatch) -> None:
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    conn.executemany(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        [
            ("2026-07-02", 30.0, "Fear", "2026-07-02T20:15:00+00:00"),
            ("2026-07-03", 75.0, "Greed", "2026-07-03T20:15:00+00:00"),
        ],
    )
    conn.executemany(
        """INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("2026-07-01", 1.1, 1.0, 1.2, "2026-07-01T22:40:00+00:00"),
            ("2026-07-02", 0.9, 0.6, 0.97, "2026-07-02T22:40:00+00:00"),
        ],
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)

    result = await research_analyzer._analyze_stock_sentiment()

    assert result["key"] == "stock_sentiment"
    assert result["name"] == "주식심리"
    assert result["score"] == 78
    assert result["level"] == "critical"
    assert result["details"]["stock_fear_greed"] == {
        "date": "2026-07-03",
        "value": 75.0,
        "rating": "Greed",
        "updated_at": "2026-07-03T20:15:00+00:00",
    }
    assert result["details"]["putcall"] == {
        "date": "2026-07-02",
        "total_pc": 0.9,
        "equity_pc": 0.6,
        "index_pc": 0.97,
        "updated_at": "2026-07-02T22:40:00+00:00",
        "used_pc": 0.6,
        "source": "equity_pc",
    }
    assert result["details"]["component_scores"] == {
        "fear_greed": 75,
        "putcall": 80,
    }


@pytest.mark.asyncio
async def test_analyze_stock_sentiment_rounds_only_final_weighted_score(monkeypatch) -> None:
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        ("2026-07-03", 74.9, "Greed", "2026-07-03T20:15:00+00:00"),
    )
    conn.execute(
        """INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("2026-07-02", 0.9, 0.6, 0.97, "2026-07-02T22:40:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)

    result = await research_analyzer._analyze_stock_sentiment()

    assert result["score"] == 77
    assert result["level"] == "critical"
    assert result["details"]["component_scores"] == {
        "fear_greed": 74.9,
        "putcall": 80.0,
    }


@pytest.mark.asyncio
async def test_analyze_stock_sentiment_clamps_putcall_component_before_weighting(monkeypatch) -> None:
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        ("2026-07-03", 0.0, "Extreme Fear", "2026-07-03T20:15:00+00:00"),
    )
    conn.execute(
        """INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("2026-07-02", 0.2, 0.0, 0.97, "2026-07-02T22:40:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)

    result = await research_analyzer._analyze_stock_sentiment()

    assert result["score"] == 50
    assert result["details"]["component_scores"]["putcall"] == 100.0


@pytest.mark.asyncio
async def test_analyze_stock_sentiment_falls_back_to_total_putcall(monkeypatch) -> None:
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        ("2026-07-03", 40.0, "Fear", "2026-07-03T20:15:00+00:00"),
    )
    conn.execute(
        """INSERT INTO cboe_putcall (date, total_pc, equity_pc, index_pc, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("2026-07-02", 0.75, None, 1.1, "2026-07-02T22:40:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)

    result = await research_analyzer._analyze_stock_sentiment()

    assert result["score"] == 45
    assert result["level"] == "bearish"
    assert result["details"]["putcall"]["used_pc"] == 0.75
    assert result["details"]["putcall"]["source"] == "total_pc"


@pytest.mark.asyncio
async def test_analyze_stock_sentiment_returns_error_category_when_input_missing(monkeypatch) -> None:
    from dashboard.backend.db import connection
    from dashboard.backend.services import research_analyzer

    conn = _memory_conn()
    conn.execute(
        """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
           VALUES (?, ?, ?, ?)""",
        ("2026-07-03", 40.0, "Fear", "2026-07-03T20:15:00+00:00"),
    )

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(connection, "get_db", fake_get_db)

    result = await research_analyzer._analyze_stock_sentiment()

    assert result["key"] == "stock_sentiment"
    assert result["name"] == "주식심리"
    assert result["score"] == 0
    assert result["level"] == "neutral"
    assert result["details"] == {}


@pytest.mark.asyncio
async def test_analyze_all_appends_stock_sentiment_without_reordering_existing_categories(monkeypatch) -> None:
    from dashboard.backend.services import research_analyzer

    expected_existing_keys = [
        "macro",
        "onchain",
        "derivatives",
        "altcoin",
        "technical",
        "market",
        "whale",
        "semiconductor_signals",
    ]

    async def fake_category(key: str) -> dict:
        return {
            "key": key,
            "name": key,
            "level": "neutral",
            "score": 0,
            "title": key,
            "summary": key,
            "details": {},
            "updated_at": "2026-07-05T00:00:00+00:00",
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
    ]:
        async def fake(key=key):
            return await fake_category(key)

        monkeypatch.setattr(research_analyzer, name, fake, raising=False)

    result = await research_analyzer.analyze_all()

    keys = [category["key"] for category in result["categories"]]
    assert keys[:8] == expected_existing_keys
    assert keys[8] == "stock_sentiment"
