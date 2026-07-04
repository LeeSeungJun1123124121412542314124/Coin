"""시뮬레이터 만료 예측 채점 테스트."""

from __future__ import annotations

import pytest

from dashboard.backend.jobs.settle_predictions import settle_expired_predictions
from dashboard.backend.utils.time_utils import iso_to_epoch_ms


@pytest.fixture
def sim_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection

    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "sim.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _insert_bar(
    conn,
    symbol: str,
    ts: str,
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO coin_ohlcv_1h (symbol, timestamp, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            iso_to_epoch_ms(ts),
            close,
            high if high is not None else close,
            low if low is not None else close,
            close,
            1000.0,
        ),
    )


def test_iso_to_epoch_ms_rejects_timezone_less_value():
    with pytest.raises(ValueError, match="timezone"):
        iso_to_epoch_ms("2026-01-01T02:30:00")


@pytest.mark.asyncio
async def test_crypto_settlement_uses_expiry_price_not_latest(sim_db):
    expiry = "2026-01-01T02:30:00+00:00"
    with sim_db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "BTCUSDT", "direction", "long", 100.0, "2026-01-01T00:00:00+00:00", expiry, "pending", expiry),
        )
        _insert_bar(conn, "BTCUSDT", "2026-01-01T02:00:00+00:00", 110.0)
        _insert_bar(conn, "BTCUSDT", "2026-01-01T03:00:00+00:00", 200.0)

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        row = conn.execute(
            """
            SELECT ss.actual_price, ss.direction_hit, sp.status
            FROM sim_settlements ss
            JOIN sim_predictions sp ON sp.id = ss.prediction_id
            """
        ).fetchone()

    assert row["actual_price"] == 110.0
    assert row["direction_hit"] == 1
    assert row["status"] == "settled"


@pytest.mark.asyncio
async def test_crypto_settlement_skips_when_no_expiry_history(sim_db, caplog):
    expiry = "2026-01-01T02:30:00+00:00"
    with sim_db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "BTCUSDT", "direction", "long", 100.0, "2026-01-01T00:00:00+00:00", expiry, "pending", expiry),
        )
        _insert_bar(conn, "BTCUSDT", "2026-01-01T03:00:00+00:00", 200.0)

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        settlement_count = conn.execute("SELECT COUNT(*) FROM sim_settlements").fetchone()[0]
        status = conn.execute("SELECT status FROM sim_predictions").fetchone()["status"]

    assert settlement_count == 0
    assert status == "pending"
    assert "가격 조회 실패" in caplog.text


@pytest.mark.asyncio
async def test_crypto_settlement_checks_sl_tp_at_expiry_not_latest(sim_db):
    expiry = "2026-01-01T02:30:00+00:00"
    with sim_db.get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "BTCUSDT", "portfolio", "long", 100.0, "2026-01-01T00:00:00+00:00", expiry, "pending", expiry),
        )
        conn.execute(
            """
            INSERT INTO sim_positions
                (prediction_id, instrument_type, quantity, leverage, stop_loss, take_profit, liquidation_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cursor.lastrowid, "futures", 1.0, 1, 90.0, 120.0, 70.0),
        )
        _insert_bar(conn, "BTCUSDT", "2026-01-01T02:00:00+00:00", 105.0, high=106.0, low=99.0)
        _insert_bar(conn, "BTCUSDT", "2026-01-01T03:00:00+00:00", 80.0, high=82.0, low=65.0)

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        row = conn.execute(
            """
            SELECT ss.actual_price, ss.liquidated, sp.status
            FROM sim_settlements ss
            JOIN sim_predictions sp ON sp.id = ss.prediction_id
            """
        ).fetchone()

    assert row["actual_price"] == 105.0
    assert row["liquidated"] == 0
    assert row["status"] == "settled"
