"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _clean_weight_env_vars(monkeypatch):
    """Isolate tests from .env file WEIGHT_ values loaded by load_dotenv()."""
    for key in ("WEIGHT_ONCHAIN", "WEIGHT_TECHNICAL", "WEIGHT_SENTIMENT"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _isolate_alert_cooldown_db(monkeypatch):
    """AlertCooldown DB를 테스트마다 새 인메모리 SQLite로 격리.

    production DB(crypto.db)의 stale 쿨다운 데이터가 테스트에 영향을 주지 않도록 한다.
    """
    _mem_conn = sqlite3.connect(":memory:")
    _mem_conn.row_factory = sqlite3.Row
    _mem_conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_cooldowns (
            key TEXT PRIMARY KEY,
            last_alerted TEXT NOT NULL,
            cooldown_type TEXT NOT NULL
        )
    """)
    _mem_conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            symbol TEXT NOT NULL,
            alert_level TEXT NOT NULL,
            alert_score REAL,
            final_score REAL,
            details TEXT,
            message_sent INTEGER DEFAULT 1
        )
    """)
    _mem_conn.commit()

    import threading
    _lock = threading.Lock()

    @contextmanager
    def _fake_get_db():
        with _lock:
            try:
                yield _mem_conn
                _mem_conn.commit()
            except Exception:
                _mem_conn.rollback()
                raise

    import app.notification_dispatcher as nd_module
    monkeypatch.setattr(nd_module, "_get_db", _fake_get_db)

    yield

    _mem_conn.close()



def _make_ohlcv(n: int, base_price: float, volatility: float, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = base_price + np.cumsum(rng.normal(0, volatility, n))
    close = np.maximum(close, base_price * 0.1)
    high = close + rng.uniform(volatility * 0.5, volatility * 1.5, n)
    low = close - rng.uniform(volatility * 0.5, volatility * 1.5, n)
    low = np.minimum(low, close)
    open_ = close - rng.normal(0, volatility * 0.3, n)
    volume = rng.uniform(1_000, 10_000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    return _make_ohlcv(100, base_price=30_000, volatility=200)


@pytest.fixture
def high_volatility_ohlcv_df() -> pd.DataFrame:
    return _make_ohlcv(100, base_price=30_000, volatility=3_000, seed=99)


@pytest.fixture
def low_volatility_ohlcv_df() -> pd.DataFrame:
    return _make_ohlcv(100, base_price=30_000, volatility=10, seed=7)
