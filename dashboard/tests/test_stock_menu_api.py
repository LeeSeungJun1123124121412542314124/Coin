from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest


@pytest.mark.asyncio
async def test_fetch_index_history_accepts_three_month_yahoo_range(monkeypatch) -> None:
    from dashboard.backend import cache
    from dashboard.backend.collectors import yahoo_finance

    cache.delete_prefix("yahoo_history")
    calls: list[tuple[str, dict]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1_704_067_200, 1_704_153_600],
                        "indicators": {"quote": [{"close": [101.12345, 102.0]}]},
                    }]
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict):
            calls.append((url, params))
            return FakeResponse()

    monkeypatch.setattr(yahoo_finance.httpx, "AsyncClient", FakeAsyncClient)

    history = await yahoo_finance.fetch_index_history("DX-Y.NYB", range="3mo")

    assert calls == [(
        "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
        {"interval": "1d", "range": "3mo"},
    )]
    assert history == [
        {"date": "2024-01-01", "close": 101.1235},
        {"date": "2024-01-02", "close": 102.0},
    ]


def test_macro_history_returns_krw_exchange_schema(monkeypatch) -> None:
    from dashboard.backend.api import market_routes

    async def fake_fetch_index_history(ticker: str, range: str | None = None):
        assert ticker == "KRW=X"
        assert range == "3mo"
        return [
            {"date": "2026-07-01", "close": 1380.1},
            {"date": "2026-07-02", "close": 1390.1},
        ]

    monkeypatch.setattr(market_routes, "fetch_index_history", fake_fetch_index_history)

    app = FastAPI()
    app.include_router(market_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/market/macro-history?ticker=KRW%3DX")

    assert response.status_code == 200
    assert response.json() == {
        "ticker": "KRW=X",
        "history": [
            {"date": "2026-07-01", "close": 1380.1},
            {"date": "2026-07-02", "close": 1390.1},
        ],
        "current": {
            "price": 1390.1,
            "change_pct": 0.72,
        },
    }


def test_macro_history_rejects_unknown_ticker() -> None:
    from dashboard.backend.api import market_routes

    app = FastAPI()
    app.include_router(market_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/market/macro-history?ticker=AAPL")

    assert response.status_code == 400


def test_market_analysis_top_level_keys_remain_stable(monkeypatch) -> None:
    from dashboard.backend.api import market_routes

    async def fake_snapshot() -> dict:
        return {"fear_greed": {}, "us_market": {}}

    async def fake_vix_btc_history() -> list[dict]:
        return []

    monkeypatch.setattr(market_routes, "_get_dashboard_snapshot", fake_snapshot)
    monkeypatch.setattr(market_routes, "generate_insights", lambda data: [])
    monkeypatch.setattr(market_routes, "_get_vix_btc_history", fake_vix_btc_history)
    monkeypatch.setattr(market_routes, "_get_latest_bot_level", lambda: None)

    app = FastAPI()
    app.include_router(market_routes.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/market-analysis")

    assert response.status_code == 200
    assert set(response.json()) == {
        "insights",
        "key_indicators",
        "vix_btc_history",
        "bot_level",
    }


@pytest.mark.asyncio
async def test_us_stock_search_accepts_yahoo_nms_exchange_and_prioritizes_exact_symbol(monkeypatch) -> None:
    from dashboard.backend.collectors import yahoo_finance

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "quotes": [
                    {
                        "exchange": "NGM",
                        "symbol": "PLA",
                        "shortname": "GraniteShares Autocallable PLTR",
                        "quoteType": "ETF",
                    },
                    {
                        "exchange": "NMS",
                        "symbol": "PLTR",
                        "shortname": "Palantir Technologies Inc.",
                        "quoteType": "EQUITY",
                    },
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict):
            assert params["q"] == "PLTR"
            return FakeResponse()

    monkeypatch.setattr(yahoo_finance.httpx, "AsyncClient", FakeAsyncClient)

    results = await yahoo_finance.search_stocks("PLTR", "us")

    assert results[:2] == [
        {"ticker": "PLTR", "name": "Palantir Technologies Inc."},
        {"ticker": "PLA", "name": "GraniteShares Autocallable PLTR"},
    ]


@pytest.mark.asyncio
async def test_lookup_stock_info_falls_back_to_chart_metadata_when_quote_summary_rejects(monkeypatch) -> None:
    from dashboard.backend.collectors import yahoo_finance

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, url: str) -> None:
            self.url = url
            self.status_code = 401 if "quoteSummary" in url else 200

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                request = httpx.Request("GET", self.url)
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("blocked", request=request, response=response)

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [{
                        "meta": {
                            "shortName": "Palantir Technologies Inc.",
                            "fullExchangeName": "NasdaqGS",
                            "exchangeName": "NMS",
                        }
                    }]
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict):
            calls.append(url)
            return FakeResponse(url)

    monkeypatch.setattr(yahoo_finance.httpx, "AsyncClient", FakeAsyncClient)

    assert await yahoo_finance.lookup_stock_info("PLTR") == {
        "name": "Palantir Technologies Inc.",
        "exchange": "NasdaqGS",
    }
    assert calls == [
        "https://query1.finance.yahoo.com/v10/finance/quoteSummary/PLTR",
        "https://query1.finance.yahoo.com/v8/finance/chart/PLTR",
    ]
