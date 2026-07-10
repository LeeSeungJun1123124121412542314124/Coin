"""선물 시뮬 펀딩비 — FR 실연동·일괄 적용·스케줄 등록 테스트.

배경: _fetch_funding_rate가 플레이스홀더(항상 0.0)였고 apply_funding_fees는
스케줄 미등록 상태였음 (PLAN_simulator.md Task 4/5 미완).
"""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dashboard.backend.db.connection import _init_schema


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _seed_futures_position(
    conn: sqlite3.Connection,
    direction: str = "long",
    quantity: float = 0.5,
    entry_price: float = 100_000.0,
) -> int:
    """pending 선물 예측 + 포지션 삽입 → position_id 반환. (계좌 1 = crypto, 자본 10000)"""
    cur = conn.execute(
        """INSERT INTO sim_predictions
           (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
           VALUES (1, 'BTCUSDT', 'portfolio', ?, ?, '2026-07-11T00:00:00+00:00',
                   '2026-08-11T00:00:00+00:00', 'pending', '2026-07-11T00:00:00+00:00')""",
        (direction, entry_price),
    )
    prediction_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO sim_positions (prediction_id, instrument_type, quantity, leverage)
           VALUES (?, 'futures', ?, 10)""",
        (prediction_id, quantity),
    )
    return cur.lastrowid


@contextmanager
def _fake_db(conn: sqlite3.Connection):
    yield conn
    conn.commit()


# ── _fetch_funding_rate 실연동 ───────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_funding_rate_uses_bybit_collector(monkeypatch) -> None:
    from dashboard.backend.services import sim_engine

    async def fake_bybit(symbol: str = "BTCUSDT", limit: int = 3):
        assert symbol == "BTCUSDT"
        assert limit == 1
        return {"symbol": symbol, "funding_rate": 0.0001, "funding_rate_pct": 0.01,
                "latest_rates": [0.0001]}

    monkeypatch.setattr(sim_engine, "fetch_funding_rate", fake_bybit)

    assert await sim_engine._fetch_funding_rate("BTCUSDT") == pytest.approx(0.0001)


@pytest.mark.asyncio
async def test_fetch_funding_rate_returns_none_on_failure(monkeypatch) -> None:
    from dashboard.backend.services import sim_engine

    async def fake_bybit(symbol: str = "BTCUSDT", limit: int = 3):
        return None  # 수집기 실패 시 None 반환 컨벤션

    monkeypatch.setattr(sim_engine, "fetch_funding_rate", fake_bybit)

    assert await sim_engine._fetch_funding_rate("BTCUSDT") is None


# ── apply_funding_fees ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_funding_fees_long_pays_when_fr_positive(monkeypatch) -> None:
    from dashboard.backend.services import sim_engine

    conn = _memory_conn()
    position_id = _seed_futures_position(conn, direction="long", quantity=0.5, entry_price=100_000.0)

    async def fake_fr(symbol: str):
        return 0.0001

    monkeypatch.setattr(sim_engine, "_fetch_funding_rate", fake_fr)
    monkeypatch.setattr(sim_engine, "get_db", lambda: _fake_db(conn))

    await sim_engine.apply_funding_fees("2026-07-11T00:00:00+00:00")

    # 펀딩비 = 0.5 × 100,000 × 0.0001 = 5.0 — 롱은 지불
    event = conn.execute("SELECT * FROM sim_funding_events WHERE position_id = ?", (position_id,)).fetchone()
    assert event["fr_value"] == pytest.approx(0.0001)
    assert event["funding_amount"] == pytest.approx(5.0)

    pos = conn.execute("SELECT funding_fee_accrued FROM sim_positions WHERE id = ?", (position_id,)).fetchone()
    assert pos["funding_fee_accrued"] == pytest.approx(-5.0)

    acct = conn.execute("SELECT capital, updated_at FROM sim_accounts WHERE id = 1").fetchone()
    assert acct["capital"] == pytest.approx(10_000.0 - 5.0)
    assert acct["updated_at"] == "2026-07-11T00:00:00+00:00"


@pytest.mark.asyncio
async def test_apply_funding_fees_short_receives_when_fr_positive(monkeypatch) -> None:
    from dashboard.backend.services import sim_engine

    conn = _memory_conn()
    position_id = _seed_futures_position(conn, direction="short", quantity=0.5, entry_price=100_000.0)

    async def fake_fr(symbol: str):
        return 0.0001

    monkeypatch.setattr(sim_engine, "_fetch_funding_rate", fake_fr)
    monkeypatch.setattr(sim_engine, "get_db", lambda: _fake_db(conn))

    await sim_engine.apply_funding_fees("2026-07-11T08:00:00+00:00")

    pos = conn.execute("SELECT funding_fee_accrued FROM sim_positions WHERE id = ?", (position_id,)).fetchone()
    assert pos["funding_fee_accrued"] == pytest.approx(+5.0)
    acct = conn.execute("SELECT capital FROM sim_accounts WHERE id = 1").fetchone()
    assert acct["capital"] == pytest.approx(10_000.0 + 5.0)


@pytest.mark.asyncio
async def test_apply_funding_fees_skips_position_when_fr_unavailable(monkeypatch) -> None:
    """FR 조회 실패 → 가짜(0.0) 이벤트를 남기지 않고 해당 포지션 스킵."""
    from dashboard.backend.services import sim_engine

    conn = _memory_conn()
    _seed_futures_position(conn)

    async def fake_fr(symbol: str):
        return None

    monkeypatch.setattr(sim_engine, "_fetch_funding_rate", fake_fr)
    monkeypatch.setattr(sim_engine, "get_db", lambda: _fake_db(conn))

    await sim_engine.apply_funding_fees("2026-07-11T00:00:00+00:00")

    assert conn.execute("SELECT COUNT(*) c FROM sim_funding_events").fetchone()["c"] == 0
    acct = conn.execute("SELECT capital FROM sim_accounts WHERE id = 1").fetchone()
    assert acct["capital"] == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_apply_funding_fees_ignores_spot_and_settled(monkeypatch) -> None:
    from dashboard.backend.services import sim_engine

    conn = _memory_conn()
    # spot 포지션
    cur = conn.execute(
        """INSERT INTO sim_predictions
           (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
           VALUES (1, 'BTCUSDT', 'portfolio', 'long', 100000, '2026-07-11T00:00:00+00:00',
                   '2026-08-11T00:00:00+00:00', 'pending', '2026-07-11T00:00:00+00:00')"""
    )
    conn.execute(
        "INSERT INTO sim_positions (prediction_id, instrument_type, quantity) VALUES (?, 'spot', 1.0)",
        (cur.lastrowid,),
    )
    # settled 선물 포지션
    cur = conn.execute(
        """INSERT INTO sim_predictions
           (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
           VALUES (1, 'BTCUSDT', 'portfolio', 'long', 100000, '2026-07-01T00:00:00+00:00',
                   '2026-07-08T00:00:00+00:00', 'settled', '2026-07-01T00:00:00+00:00')"""
    )
    conn.execute(
        "INSERT INTO sim_positions (prediction_id, instrument_type, quantity, leverage) VALUES (?, 'futures', 1.0, 5)",
        (cur.lastrowid,),
    )

    async def fake_fr(symbol: str):
        return 0.0001

    monkeypatch.setattr(sim_engine, "_fetch_funding_rate", fake_fr)
    monkeypatch.setattr(sim_engine, "get_db", lambda: _fake_db(conn))

    await sim_engine.apply_funding_fees("2026-07-11T00:00:00+00:00")

    assert conn.execute("SELECT COUNT(*) c FROM sim_funding_events").fetchone()["c"] == 0


# ── 스케줄 등록 ──────────────────────────────────────────────────


def test_sim_funding_job_is_registered_at_utc_0_8_16() -> None:
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")

    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())

    job = scheduler.get_job("sim_funding")
    assert job is not None
    hours = {e.first for e in job.trigger.fields[5].expressions}
    assert hours == {0, 8, 16}
    assert job.trigger.fields[6].expressions[0].first == 2
    assert job.trigger.timezone.utcoffset(None).total_seconds() == 0
