"""네이버 파이낸스 fchart API — 한국 주식 OHLCV 히스토리."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_PERIOD_COUNT = {"1w": 10, "1m": 30, "3m": 90, "6m": 180, "1y": 365}


def _strip_suffix(ticker: str) -> str:
    """'005930.KS' → '005930'"""
    return ticker.split(".")[0]


def _parse_date(raw: str) -> str:
    """'20260413' → '2026-04-13'"""
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


@cached(ttl=3600, key_prefix="naver_ohlcv")
async def fetch_naver_ohlcv(ticker: str, period: str = "3m") -> list[dict] | None:
    """네이버 파이낸스에서 한국 주식 일봉 OHLCV 조회.

    Args:
        ticker: 야후 형식 티커 ('005930.KS') 또는 6자리 코드 ('005930')
        period: '3m' | '6m' | '1y'

    Returns:
        [{"date", "open", "high", "low", "close", "volume"}] 또는 None
    """
    code = _strip_suffix(ticker)
    count = _PERIOD_COUNT.get(period, 90)
    url = "https://fchart.stock.naver.com/sise.nhn"
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = await client.get(url, params={
                "symbol": code,
                "timeframe": "day",
                "count": count,
                "requestType": "0",
            })
            resp.raise_for_status()
            # 네이버 응답은 EUC-KR 인코딩
            text = resp.content.decode("euc-kr", errors="replace")
            root = ET.fromstring(text)
            rows = []
            for item in root.iter("item"):
                raw = item.get("data", "")
                parts = raw.split("|")
                if len(parts) < 6:
                    continue
                date_str, o, h, l, c, v = parts[:6]
                try:
                    rows.append({
                        "date": _parse_date(date_str),
                        "open": int(o),
                        "high": int(h),
                        "low": int(l),
                        "close": int(c),
                        "volume": int(v),
                    })
                except (ValueError, IndexError):
                    continue
            return rows if rows else None
    except Exception as e:
        logger.warning("네이버 OHLCV 조회 실패 (%s): %s", ticker, e)
        return None
