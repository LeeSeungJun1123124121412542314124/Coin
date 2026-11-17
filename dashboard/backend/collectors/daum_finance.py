"""다음 금융 시장지수 일별 API — KOSPI/KOSDAQ 거래대금.

네이버 PC sise_index_day 페이지가 410 Gone으로 종료돼 대체(2026-11).
accTradePrice(백만원)가 기존 네이버 거래대금과 확정일 기준 완전 일치함을 운영 DB로 확인.
"""

from __future__ import annotations

import httpx

_DAUM_MARKET_DAYS_URL = "https://finance.daum.net/api/market_index/days"
# Referer 없으면 거부됨
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.daum.net/domestic"}
_MAX_WINDOW_DAYS = 60


async def fetch_market_volume(market: str, days: int = 30) -> list[dict]:
    """KOSPI/KOSDAQ 최근 거래일별 거래대금(조원)을 조회한다 (최대 60영업일)."""
    if market not in ("KOSPI", "KOSDAQ"):
        raise ValueError("market은 KOSPI 또는 KOSDAQ만 허용됩니다")

    target_days = min(max(1, days), _MAX_WINDOW_DAYS)
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        resp = await client.get(
            _DAUM_MARKET_DAYS_URL,
            params={"page": 1, "perPage": target_days, "market": market, "pagination": "true"},
        )
        resp.raise_for_status()

    return [
        {"date": item["date"][:10], "value": round(item["accTradePrice"] / 1_000_000, 4)}
        for item in resp.json()["data"]
    ]
