"""네이버 파이낸스 fchart API — 한국 주식 OHLCV 히스토리 및 종목 검색."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from math import ceil
from zoneinfo import ZoneInfo

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
_NAVER_INVESTOR_URL = "https://finance.naver.com/sise/investorDealTrendDay.nhn"
_NAVER_MARKET_VOLUME_URL = "https://finance.naver.com/sise/sise_index_day.naver"
_INVESTOR_MARKET_SOSOK: dict[str, str] = {
    "KOSPI": "",
    "KOSDAQ": "02",
}
_MARKET_VOLUME_CODE: dict[str, str] = {
    "KOSPI": "KOSPI",
    "KOSDAQ": "KOSDAQ",
}
_INVESTOR_DATE_RE = re.compile(r"^(?:\d{2}|\d{4})\.\d{2}\.\d{2}$")


class _TableRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            text = "".join(self._current_cell).strip()
            self._current_row.append(re.sub(r"\s+", " ", text))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None


def _parse_investor_date(raw: str) -> str:
    year, month, day = raw.split(".")
    if len(year) == 2:
        year = f"20{year}"
    return f"{year}-{month}-{day}"


def _parse_investor_number(raw: str) -> float:
    return float(raw.replace(",", "").strip())


def parse_investor_flow_html(html: str) -> list[dict]:
    """네이버 투자자별 매매동향 HTML에서 핵심 순매수 컬럼을 파싱한다."""
    parser = _TableRowParser()
    parser.feed(html)

    records: list[dict] = []
    for row in parser.rows:
        if len(row) < 4 or not _INVESTOR_DATE_RE.match(row[0]):
            continue
        try:
            records.append({
                "date": _parse_investor_date(row[0]),
                "individual_net": _parse_investor_number(row[1]),
                "foreign_net": _parse_investor_number(row[2]),
                "institution_net": _parse_investor_number(row[3]),
            })
        except ValueError:
            continue
    return records


def parse_market_volume_html(html: str) -> list[dict]:
    """네이버 시장 일별시세 HTML에서 거래대금(조원)을 추출한다."""
    parser = _TableRowParser()
    parser.feed(html)

    records: list[dict] = []
    for row in parser.rows:
        if len(row) < 6 or not _INVESTOR_DATE_RE.match(row[0]):
            continue
        try:
            records.append({
                "date": _parse_investor_date(row[0]),
                "value": round(_parse_investor_number(row[5]) / 1_000_000, 4),
            })
        except ValueError:
            continue
    return records


async def fetch_investor_deal_trend(market: str, days: int = 30) -> list[dict]:
    """네이버 일자별 순매수 페이지에서 최근 투자자 수급을 조회한다."""
    if market not in _INVESTOR_MARKET_SOSOK:
        raise ValueError("market은 KOSPI 또는 KOSDAQ만 허용됩니다")

    target_days = min(max(1, days), 30)
    pages = max(3, ceil(target_days / 10))
    bizdate = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    records: list[dict] = []
    seen_dates: set[str] = set()

    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for page in range(1, pages + 1):
            resp = await client.get(
                _NAVER_INVESTOR_URL,
                params={
                    "bizdate": bizdate,
                    "sosok": _INVESTOR_MARKET_SOSOK[market],
                    "page": page,
                },
            )
            resp.raise_for_status()
            html = resp.content.decode("euc-kr", errors="replace")
            for record in parse_investor_flow_html(html):
                if record["date"] in seen_dates:
                    continue
                seen_dates.add(record["date"])
                records.append(record)
                if len(records) >= target_days:
                    return records

    return records[:target_days]


async def fetch_market_volume(market: str, days: int = 30) -> list[dict]:
    """네이버 시장 일별시세에서 KOSPI/KOSDAQ 거래대금(조원)을 조회한다."""
    if market not in _MARKET_VOLUME_CODE:
        raise ValueError("market은 KOSPI 또는 KOSDAQ만 허용됩니다")

    target_days = min(max(1, days), 30)
    pages = max(3, ceil(target_days / 10))
    records: list[dict] = []
    seen_dates: set[str] = set()

    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for page in range(1, pages + 1):
            resp = await client.get(
                _NAVER_MARKET_VOLUME_URL,
                params={"code": _MARKET_VOLUME_CODE[market], "page": page},
            )
            resp.raise_for_status()
            html = resp.content.decode("euc-kr", errors="replace")
            for record in parse_market_volume_html(html):
                if record["date"] in seen_dates:
                    continue
                seen_dates.add(record["date"])
                records.append(record)
                if len(records) >= target_days:
                    return records

    return records[:target_days]


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
                date_str, o, h, lo, c, v = parts[:6]
                try:
                    rows.append({
                        "date": _parse_date(date_str),
                        "open": int(o),
                        "high": int(h),
                        "low": int(lo),
                        "close": int(c),
                        "volume": int(v),
                    })
                except (ValueError, IndexError):
                    continue
            return rows if rows else None
    except Exception as e:
        logger.warning("네이버 OHLCV 조회 실패 (%s): %s", ticker, e)
        return None
