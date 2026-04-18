"""Yahoo Finance — 미국 시장 지표 10종 (비공식 API + yfinance 폴백)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_TICKERS = {
    "^GSPC":    {"name": "S&P 500",    "category": "us_market"},
    "^IXIC":    {"name": "NASDAQ",     "category": "us_market"},
    "^RUT":     {"name": "Russell 2K", "category": "us_market"},
    "^VIX":     {"name": "VIX",        "category": "volatility"},
    "^MOVE":    {"name": "MOVE",       "category": "volatility"},
    "DX-Y.NYB": {"name": "DXY",        "category": "dollar"},
    "^TNX":     {"name": "US 10Y",     "category": "bond"},
    "GC=F":     {"name": "Gold",       "category": "commodity"},
    "SI=F":     {"name": "Silver",     "category": "commodity"},
    "^KS11":    {"name": "KOSPI",      "category": "korea"},
    "^KQ11":    {"name": "KOSDAQ",    "category": "korea"},
}


async def _fetch_single_yahoo(client: httpx.AsyncClient, ticker: str) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        resp = await client.get(url, params={"interval": "1d", "range": "5d"})
        resp.raise_for_status()
        data = resp.json()
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if not closes:
            return None
        current = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else closes[-1]
        change_pct = (current - prev) / prev * 100 if prev else 0
        return {
            "ticker": ticker,
            "name": _TICKERS[ticker]["name"],
            "category": _TICKERS[ticker]["category"],
            "price": round(current, 4),
            "change_pct": round(change_pct, 2),
            "sparkline": [round(c, 4) for c in closes[-5:]],
        }
    except Exception:
        return None


async def _fetch_single_yfinance(ticker: str) -> dict | None:
    """yfinance 폴백."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return None
        closes = hist["Close"].tolist()
        current = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else closes[-1]
        change_pct = (current - prev) / prev * 100 if prev else 0
        return {
            "ticker": ticker,
            "name": _TICKERS[ticker]["name"],
            "category": _TICKERS[ticker]["category"],
            "price": round(current, 4),
            "change_pct": round(change_pct, 2),
            "sparkline": [round(c, 4) for c in closes[-5:]],
        }
    except Exception as e:
        logger.error("yfinance 폴백 실패 (%s): %s", ticker, e)
        return None


@cached(ttl=300, key_prefix="yahoo_market")
async def fetch_us_market() -> list | None:
    """10개 미국 시장 지표 조회."""
    import asyncio

    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = [_fetch_single_yahoo(client, t) for t in _TICKERS]
        results = await asyncio.gather(*tasks)

    # Yahoo 실패한 항목은 yfinance로 재시도
    import asyncio as _asyncio
    final = []
    fallback_tasks = []
    for i, (ticker, res) in enumerate(zip(_TICKERS.keys(), results)):
        if res is not None:
            final.append((i, res))
        else:
            fallback_tasks.append((i, ticker))

    if fallback_tasks:
        fb_results = await _asyncio.gather(*[_fetch_single_yfinance(t) for _, t in fallback_tasks])
        for (i, _), res in zip(fallback_tasks, fb_results):
            if res:
                final.append((i, res))

    final.sort(key=lambda x: x[0])
    return [r for _, r in final] if final else None


@cached(ttl=3600, key_prefix="yahoo_history")
async def fetch_index_history(ticker: str, days: int = 30) -> list[dict] | None:
    """지수 30일 종가 히스토리 — 모달 차트용."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url, params={"interval": "1d", "range": f"{days}d"})
            resp.raise_for_status()
            result = resp.json()["chart"]["result"][0]
            timestamps = result.get("timestamp", [])
            closes = result["indicators"]["quote"][0].get("close", [])
            return [
                {"date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), "close": round(c, 4)}
                for t, c in zip(timestamps, closes)
                if c is not None
            ]
    except Exception as e:
        logger.warning("지수 히스토리 조회 실패 (%s): %s", ticker, e)
        return None
