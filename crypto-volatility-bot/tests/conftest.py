"""Shared pytest fixtures."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _clean_weight_env_vars(monkeypatch):
    """Isolate tests from .env file WEIGHT_ values loaded by load_dotenv()."""
    for key in ("WEIGHT_ONCHAIN", "WEIGHT_TECHNICAL", "WEIGHT_SENTIMENT"):
        monkeypatch.delenv(key, raising=False)



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
