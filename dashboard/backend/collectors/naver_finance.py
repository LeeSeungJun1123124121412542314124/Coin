"""네이버 파이낸스 fchart API — 한국 주식 OHLCV 히스토리 및 종목 검색."""

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


# KOSPI/KOSDAQ → Yahoo Finance 티커 suffix 매핑
_MARKET_SUFFIX: dict[str, str] = {
    "KOSPI": ".KS",
    "KOSDAQ": ".KQ",
}

# 네이버 자동완성 API — 응답은 UTF-8 JSON
_NAVER_AC_URL = "https://ac.stock.naver.com/ac"


async def search_naver_stocks(query: str) -> list[dict]:
    """네이버 금융 자동완성 API로 한국 주식 검색.

    Args:
        query: 검색어 (한글/영문 종목명 또는 종목코드)

    Returns:
        [{"ticker": "005930.KS", "name": "삼성전자"}, ...] (최대 5개)
        실패 시 빈 리스트 반환.
    """
    try:
        async with httpx.AsyncClient(
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = await client.get(_NAVER_AC_URL, params={
                "q": query,
                "target": "stock",
            })
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("items", [])[:5]:
            code = item.get("code", "")
            name = item.get("name", "")
            type_code = item.get("typeCode", "")  # "KOSPI" or "KOSDAQ"
            suffix = _MARKET_SUFFIX.get(type_code, ".KS")  # 알 수 없는 시장은 .KS로 기본 처리
            if code and name:
                results.append({"ticker": f"{code}{suffix}", "name": name})
        return results
    except Exception as e:
        logger.warning("네이버 종목 검색 실패 (%s): %s", query, e)
        return []


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
