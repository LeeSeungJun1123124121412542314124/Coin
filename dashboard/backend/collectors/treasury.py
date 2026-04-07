"""미국 국채 경매 일정 수집기.

TreasuryDirect 공개 API 사용 (키 불필요).
향후 4주 예정 경매를 조회한다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://www.treasurydirect.gov/TA_WS/securities/announced"


@cached(3600, "treasury_auctions")
async def fetch_upcoming_auctions(days: int = 28) -> list[dict[str, Any]]:
    """향후 N일 국채 경매 일정 조회.

    Returns list of:
      {date, type, term, cusip, offering_amount (십억 달러), auction_date}
    """
    try:
        today = date.today()
        end_date = today + timedelta(days=days)

        params = {
            "startDate": today.strftime("%m/%d/%Y"),
            "endDate": end_date.strftime("%m/%d/%Y"),
            "format": "json",
            "dateFieldName": "auctionDate",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list):
            return []

        result = []
        for item in data:
            # 주요 정보만 추출
            auction_date = item.get("auctionDate", "")[:10]
            security_type = item.get("securityType", "")
            security_term = item.get("securityTerm", "")
            offering_amount = item.get("offeringAmount")

            if not auction_date:
                continue

            # 금액: 달러 → 십억 달러
            amount_b = None
            if offering_amount:
                try:
                    amount_b = round(float(offering_amount) / 1e9, 1)
                except (TypeError, ValueError):
                    pass

            result.append({
                "auction_date": auction_date,
                "type": security_type,
                "term": security_term,
                "offering_amount_b": amount_b,
                "cusip": item.get("cusip", ""),
            })

        # 날짜 순 정렬
        result.sort(key=lambda x: x["auction_date"])
        return result

    except Exception as e:
        logger.error("국채 경매 일정 조회 실패: %s", e)
        return []


@cached(3600, "treasury_recent")
async def fetch_recent_auctions(limit: int = 20) -> list[dict[str, Any]]:
    """최근 완료된 국채 경매 결과 조회."""
    try:
        params = {
            "format": "json",
            "dateFieldName": "auctionDate",
            "startDate": (date.today() - timedelta(days=60)).strftime("%m/%d/%Y"),
            "endDate": date.today().strftime("%m/%d/%Y"),
            "type": "Note,Bond,Bill",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list):
            return []

        result = []
        for item in data[:limit]:
            auction_date = item.get("auctionDate", "")[:10]
            bid_to_cover = item.get("bidToCoverRatio")

            amount_b = None
            offering_amount = item.get("offeringAmount")
            if offering_amount:
                try:
                    amount_b = round(float(offering_amount) / 1e9, 1)
                except (TypeError, ValueError):
                    pass

            result.append({
                "auction_date": auction_date,
                "type": item.get("securityType", ""),
                "term": item.get("securityTerm", ""),
                "offering_amount_b": amount_b,
                "bid_to_cover": float(bid_to_cover) if bid_to_cover else None,
                "high_yield": item.get("highYield"),
            })

        result.sort(key=lambda x: x["auction_date"], reverse=True)
        return result

    except Exception as e:
        logger.error("최근 국채 경매 조회 실패: %s", e)
        return []
