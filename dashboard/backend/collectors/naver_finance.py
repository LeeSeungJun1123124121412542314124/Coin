"""네이버 파이낸스 fchart API — 한국 주식 OHLCV 히스토리."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

# (timeframe, count) 매핑 — 네이버 fchart는 day/week/month 모두 지원
_INTERVAL_MAP: dict[str, tuple[str, int]] = {
    "1d":  ("day",   200),
    "1wk": ("week",  200),
    "1mo": ("month", 120),
}


def _strip_suffix(ticker: str) -> str:
    """'005930.KS' → '005930'"""
    return ticker.split(".")[0]


def _parse_date(raw: str) -> str:
    """'20260413' → '2026-04-13'"""
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


@cached(ttl=3600, key_prefix="naver_ohlcv")
async def fetch_naver_ohlcv(ticker: str, interval: str = "1d") -> list[dict] | None:
    """네이버 파이낸스에서 한국 주식 OHLCV 히스토리 조회.

    Args:
        ticker:   야후 형식 티커 ('005930.KS') 또는 6자리 코드 ('005930')
        interval: '1d' (일봉) | '1wk' (주봉) | '1mo' (월봉). 기본값 '1d'.

    Returns:
        [{"date", "open", "high", "low", "close", "volume"}] 또는 None
    """
    code = _strip_suffix(ticker)
    timeframe, count = _INTERVAL_MAP.get(interval, ("day", 200))
    url = "https://fchart.stock.naver.com/sise.nhn"
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = await client.get(url, params={
                "symbol": code,
                "timeframe": timeframe,
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
