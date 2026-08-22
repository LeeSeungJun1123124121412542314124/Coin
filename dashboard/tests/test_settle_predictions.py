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


@pytest.mark.asyncio
async def test_crypto_settlement_uses_stop_loss_price_when_sl_hit(sim_db):
    """만료 종가가 반등해도 손절가 터치 시 SL 가격으로 정산해야 한다 (버그 회귀 테스트).

    과거에는 trigger='stop_loss'를 무시하고 만료 종가(105)로 정산해
    실제 손실(-100)을 수익(+50)으로 계산했다.
    """
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
            (cursor.lastrowid, "futures", 1.0, 10, 90.0, None, None),
        )
        # 만료 시점 봉: low 85로 손절가(90) 터치 후 종가 105로 마감
        _insert_bar(conn, "BTCUSDT", "2026-01-01T02:00:00+00:00", 105.0, high=106.0, low=85.0)

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        row = conn.execute(
            """
            SELECT ss.actual_price, ss.pnl, ss.liquidated, sp.status
            FROM sim_settlements ss
            JOIN sim_predictions sp ON sp.id = ss.prediction_id
            """
        ).fetchone()

    # pnl = (90 - 100) × 1.0 × 10배 = -100
    assert row["actual_price"] == 90.0
    assert row["pnl"] == pytest.approx(-100.0)
    assert row["liquidated"] == 0
    assert row["status"] == "settled"


@pytest.mark.asyncio
async def test_crypto_settlement_uses_take_profit_price_when_tp_hit(sim_db):
    expiry = "2026-01-01T02:30:00+00:00"
    with sim_db.get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "BTCUSDT", "portfolio", "short", 100.0, "2026-01-01T00:00:00+00:00", expiry, "pending", expiry),
        )
        conn.execute(
            """
            INSERT INTO sim_positions
                (prediction_id, instrument_type, quantity, leverage, stop_loss, take_profit, liquidation_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cursor.lastrowid, "futures", 1.0, 5, None, 80.0, None),
        )
        # 만료 시점 봉: 숏 포지션 TP(80) 터치 — low 75, 종가 85
        _insert_bar(conn, "BTCUSDT", "2026-01-01T02:00:00+00:00", 110.0, high=125.0, low=75.0)

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        row = conn.execute(
            """
            SELECT ss.actual_price, ss.pnl, ss.liquidated, sp.status
            FROM sim_settlements ss
            JOIN sim_predictions sp ON sp.id = ss.prediction_id
            """
        ).fetchone()

    # pnl = (80 - 100) × 1.0 × (-1 방향) × 5배 = +100
    assert row["actual_price"] == 80.0
    assert row["pnl"] == pytest.approx(100.0)
    assert row["liquidated"] == 0
    assert row["status"] == "settled"


# ── 주식 정산 가격 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kr_stock_settlement_uses_expiry_date_bar_not_latest(sim_db, monkeypatch):
    """스케줄러 중단 후 재개해도 만료일 종가로 채점되는지 (버그 회귀 테스트).

    과거에는 항상 최신 일봉 close로 채점해, 중단 기간 만료된 예측이
    재개 시점 가격으로 왜곡 정산됐다.
    """
    expiry = "2026-01-05T00:00:00+00:00"
    with sim_db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (2, "005930.KS", "direction", "long", 70_000.0, "2026-01-02T00:00:00+00:00", expiry, "pending", expiry),
        )

    async def fake_naver_ohlcv(ticker: str, interval: str = "1d"):
        return [
            {"date": "2026-01-02", "open": 70_000, "high": 71_000, "low": 69_500, "close": 70_000, "volume": 1_000},
            {"date": "2026-01-05", "open": 71_000, "high": 72_000, "low": 70_000, "close": 71_000, "volume": 1_000},
            # 재개 시점(1/6)에 조회되는 이후 봉 — 만료일 이하가 아니므로 제외 대상
            {"date": "2026-01-06", "open": 72_000, "high": 73_000, "low": 71_500, "close": 73_000, "volume": 1_000},
        ]

    monkeypatch.setattr(
        "dashboard.backend.collectors.naver_finance.fetch_naver_ohlcv", fake_naver_ohlcv
    )

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        row = conn.execute(
            """
            SELECT ss.actual_price, ss.direction_hit, sp.status
            FROM sim_settlements ss
            JOIN sim_predictions sp ON sp.id = ss.prediction_id
            """
        ).fetchone()

    # 만료일(1/5) 이하 마지막 봉인 71,000으로 채점 — 재개 시점 봉(73,000) 아님
    assert row["actual_price"] == 71_000.0
    assert row["direction_hit"] == 1
    assert row["status"] == "settled"


@pytest.mark.asyncio
async def test_us_stock_settlement_skips_when_no_bar_on_or_before_expiry(sim_db, monkeypatch):
    """만료일 이전 일봉이 하나도 없으면 채점하지 않고 pending 유지."""
    expiry = "2026-01-05T00:00:00+00:00"
    with sim_db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (3, "AAPL", "direction", "long", 200.0, "2026-01-04T00:00:00+00:00", expiry, "pending", expiry),
        )

    async def fake_yahoo_ohlcv(ticker: str, interval: str = "1d"):
        # 히스토리 전체가 만료일 이후인 경우 (신규 상장 등)
        return [
            {"date": "2026-01-06", "open": 200, "high": 205, "low": 199, "close": 204, "volume": 1_000},
        ]

    monkeypatch.setattr(
        "dashboard.backend.collectors.yahoo_finance.fetch_stock_ohlcv", fake_yahoo_ohlcv
    )

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        settlement_count = conn.execute("SELECT COUNT(*) FROM sim_settlements").fetchone()[0]
        status = conn.execute("SELECT status FROM sim_predictions").fetchone()["status"]

    assert settlement_count == 0
    assert status == "pending"


@pytest.mark.asyncio
async def test_us_stock_settlement_ignores_unfinished_session_bar(sim_db, monkeypatch):
    """만료 시각이 미국장 마감 전이면 아직 진행 중인 당일 봉을 쓰면 안 된다.

    UTC 날짜만 잘라 비교하면 만료가 UTC 00:00~20:00 구간일 때
    아직 개장도 안 한 그날 봉이 필터를 통과해 최대 1거래일 look-ahead가 생긴다.
    """
    # 02:00 UTC = 전일 22:00 ET (전일 장 마감 후) → 전일 종가로 채점돼야 함
    expiry = "2026-08-14T02:00:00+00:00"
    with sim_db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, entry_price, entry_time, expiry_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (3, "AAPL", "direction", "long", 200.0, "2026-08-07T00:00:00+00:00", expiry, "pending", expiry),
        )

    async def fake_yahoo_ohlcv(ticker: str, interval: str = "1d"):
        # 정산이 늦게 돌아 만료일 당일 봉까지 수집된 상황
        return [
            {"date": "2026-08-13", "open": 218, "high": 222, "low": 217, "close": 220.0, "volume": 1_000},
            {"date": "2026-08-14", "open": 221, "high": 252, "low": 220, "close": 250.0, "volume": 1_000},
        ]

    monkeypatch.setattr(
        "dashboard.backend.collectors.yahoo_finance.fetch_stock_ohlcv", fake_yahoo_ohlcv
    )

    await settle_expired_predictions()

    with sim_db.get_db() as conn:
        row = conn.execute("SELECT actual_price FROM sim_settlements").fetchone()

    assert row["actual_price"] == 220.0
