"""Tests for DataCollector — 6 tests (mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.data.data_collector import DataCollector


@pytest.fixture
def collector() -> DataCollector:
    return DataCollector(
        bybit_api_key=None,
        bybit_api_secret=None,
    )


def _make_httpx_mock(json_data: dict | None = None, raise_exc: Exception | None = None):
    """httpx.AsyncClient async context manager mock 생성 헬퍼.

    httpx.AsyncClient(...)는 async context manager를 반환.
    async with ... as client: 에서 client.get(...)는 awaitable.
    httpx.Response.json()는 동기 메서드 → MagicMock 사용.
    """
    mock_resp = MagicMock()  # httpx.Response는 동기 객체
    if json_data is not None:
        mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    if raise_exc is not None:
        mock_client.get = AsyncMock(side_effect=raise_exc)
    else:
        mock_client.get = AsyncMock(return_value=mock_resp)

    # async with httpx.AsyncClient(...) as client: 패턴 지원
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    return mock_cm


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
    @pytest.mark.asyncio
    async def test_returns_int(self, collector):
        mock_cm = _make_httpx_mock(json_data={"data": [{"value": "42"}]})
        with patch("app.data.data_collector.httpx.AsyncClient", return_value=mock_cm):
            result = await collector.fetch_fear_greed()
        assert result == 42

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, collector):
        mock_cm = _make_httpx_mock(raise_exc=Exception("timeout"))
        with patch("app.data.data_collector.httpx.AsyncClient", return_value=mock_cm):
            result = await collector.fetch_fear_greed()
        assert result is None


class TestFetchOnchainData:
    @pytest.mark.asyncio
    async def test_returns_dict(self, collector):
        mock_cm = _make_httpx_mock(json_data={
            "data": [{"FlowInExNtv": "1000", "FlowOutExNtv": "800", "AdrActCnt": "500"}]
        })
        with patch("app.data.data_collector.httpx.AsyncClient", return_value=mock_cm):
            result = await collector.fetch_onchain_data("BTC")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, collector):
        mock_cm = _make_httpx_mock(raise_exc=Exception("timeout"))
        with patch("app.data.data_collector.httpx.AsyncClient", return_value=mock_cm):
            result = await collector.fetch_onchain_data("BTC")
        assert result is None
