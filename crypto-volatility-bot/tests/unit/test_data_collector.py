"""Tests for DataCollector — 6 tests (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.data_collector import DataCollector


@pytest.fixture
def collector() -> DataCollector:
    return DataCollector(
        bybit_api_key=None,
        bybit_api_secret=None,
    )


class TestFetchOhlcv:
    def test_returns_dataframe(self, collector):
        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.return_value = [
            [1_700_000_000_000, 30000, 31000, 29000, 30500, 1000.0]
        ] * 100
        with patch("app.data.data_collector.ccxt.bybit", return_value=mock_exchange):
            df = collector.fetch_ohlcv("BTC/USDT", limit=100)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 100

    def test_api_error_returns_none(self, collector):
        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.side_effect = Exception("Network error")
        with patch("app.data.data_collector.ccxt.bybit", return_value=mock_exchange):
            result = collector.fetch_ohlcv("BTC/USDT")
        assert result is None


class TestFetchFearGreed:
    def test_returns_int(self, collector):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"value": "42"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("app.data.data_collector.requests.get", return_value=mock_resp):
            result = collector.fetch_fear_greed()
        assert result == 42

    def test_api_error_returns_none(self, collector):
        with patch("app.data.data_collector.requests.get", side_effect=Exception("timeout")):
            result = collector.fetch_fear_greed()
        assert result is None


class TestFetchOnchainData:
    def test_returns_dict(self, collector):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"exchange_inflow": 1000, "exchange_outflow": 800}]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("app.data.data_collector.requests.get", return_value=mock_resp):
            result = collector.fetch_onchain_data("BTC")
        assert isinstance(result, dict)

    def test_api_error_returns_none(self, collector):
        with patch("app.data.data_collector.requests.get", side_effect=Exception("timeout")):
            result = collector.fetch_onchain_data("BTC")
        assert result is None
