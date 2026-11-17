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
# 지수 투자자 수급 — 모바일 JSON API (PC investorDealTrendDay는 2026-09 이후 410 Gone)
_NAVER_INDEX_PRICE_URL = "https://m.stock.naver.com/api/index/{market}/price"
_NAVER_INDEX_TREND_URL = "https://m.stock.naver.com/api/index/{market}/trend"
# 종목별 투자자 매매동향 — 모바일 JSON API (순매매량 기준, 주 단위)
_NAVER_STOCK_TREND_URL = "https://m.stock.naver.com/api/stock/{code}/trend"
_MAX_WINDOW_DAYS = 60


def _parse_investor_number(raw: str) -> float:
    return float(raw.replace(",", "").strip())


async def fetch_investor_deal_trend(market: str, days: int = 30) -> list[dict]:
    """네이버 모바일 지수 API에서 최근 거래일별 투자자 순매수(억원)를 조회한다 (최대 60영업일).

    trend는 하루 1건만 주고 휴장일·주말 bizdate에도 에러 대신 0/0/0을 돌려주므로,
    price 응답의 거래일 목록에 있는 날짜만 요청한다.
    """
    if market not in ("KOSPI", "KOSDAQ"):
        raise ValueError("market은 KOSPI 또는 KOSDAQ만 허용됩니다")

    target_days = min(max(1, days), _MAX_WINDOW_DAYS)
    records: list[dict] = []

    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(
            _NAVER_INDEX_PRICE_URL.format(market=market),
            params={"pageSize": target_days, "page": 1},
        )
        resp.raise_for_status()
        trading_days = [item["localTradedAt"] for item in resp.json()]

        for day in trading_days:
            bizdate = day.replace("-", "")
            resp = await client.get(
                _NAVER_INDEX_TREND_URL.format(market=market),
                params={"bizdate": bizdate},
            )
            resp.raise_for_status()
            item = resp.json()
            if item.get("bizdate") != bizdate:
                logger.warning("네이버 수급 응답 날짜 불일치: 요청=%s 응답=%s — 스킵", bizdate, item.get("bizdate"))
                continue
            records.append({
                "date": day,
                "individual_net": _parse_investor_number(item["personalValue"]),
                "foreign_net": _parse_investor_number(item["foreignValue"]),
                "institution_net": _parse_investor_number(item["institutionalValue"]),
            })

    return records


def parse_stock_trend_json(items: list) -> list[dict]:
    """네이버 모바일 trend JSON → 일별 순매수 금액(억원, 순매매량×종가 환산) 레코드."""
    records: list[dict] = []
    for item in items:
        try:
            close = _parse_investor_number(item["closePrice"])
            records.append({
                "date": _parse_date(item["bizdate"]),
                "foreign_net": round(_parse_investor_number(item["foreignerPureBuyQuant"]) * close / 1e8, 1),
                "institution_net": round(_parse_investor_number(item["organPureBuyQuant"]) * close / 1e8, 1),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return records


async def fetch_stock_investor_trend(code: str, days: int = 30) -> list[dict]:
    """네이버 모바일 API에서 종목별 투자자 순매수 금액(억원)을 조회한다 (최대 30영업일)."""
    target_days = min(max(1, days), 30)
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(
            _NAVER_STOCK_TREND_URL.format(code=code),
            params={"pageSize": target_days, "page": 1},
        )
        resp.raise_for_status()
        return parse_stock_trend_json(resp.json())



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
