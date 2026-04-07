"""FRED API 수집기 — TGA, M2, SOMA 데이터.

FRED Series IDs:
  - TGA (재무부 일반 계좌): WTREGEN  (주간, 십억 달러)
  - M2 통화량:              M2SL     (월간, 십억 달러)
  - SOMA 보유량:            WALCL    (주간, 백만 달러)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://api.stlouisfed.org/fred/series/observations"
_API_KEY = os.environ.get("FRED_API_KEY", "")


async def _fetch_series(series_id: str, limit: int = 52) -> list[dict[str, Any]]:
    """FRED 시계열 데이터 조회."""
    if not _API_KEY:
        logger.warning("FRED_API_KEY 미설정")
        return []

    params = {
        "series_id": series_id,
        "api_key": _API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        observations = data.get("observations", [])
        result = []
        for obs in reversed(observations):  # 오래된 순
            val = obs.get("value", ".")
            if val == ".":
                continue
            result.append({"date": obs["date"], "value": float(val)})
        return result

    except Exception as e:
        logger.error("FRED %s 조회 실패: %s", series_id, e)
        return []


@cached(86400, "fred_tga")
async def fetch_tga(limit: int = 104) -> list[dict]:
    """TGA 잔고 (주간, 십억 달러). 최근 2년."""
    return await _fetch_series("WTREGEN", limit)


@cached(86400, "fred_m2")
async def fetch_m2(limit: int = 60) -> list[dict]:
    """M2 통화량 (월간, 십억 달러). 최근 5년."""
    return await _fetch_series("M2SL", limit)


@cached(86400, "fred_soma")
async def fetch_soma(limit: int = 104) -> list[dict]:
    """연준 대차대조표 총자산 (주간, 백만 달러). WALCL 사용."""
    return await _fetch_series("WALCL", limit)


def calc_tga_yoy(tga_data: list[dict]) -> list[dict]:
    """TGA YoY 변화율 계산 (현재 - 52주 전 / 52주 전 × 100)."""
    if len(tga_data) < 53:
        return []

    result = []
    for i in range(52, len(tga_data)):
        curr = tga_data[i]["value"]
        prev = tga_data[i - 52]["value"]
        if prev == 0:
            continue
        yoy = (curr - prev) / prev * 100
        result.append({
            "date": tga_data[i]["date"],
            "value": curr,
            "yoy_pct": round(yoy, 2),
        })
    return result


def calc_m2_yoy(m2_data: list[dict]) -> list[dict]:
    """M2 YoY 변화율 계산 (12개월 기준)."""
    if len(m2_data) < 13:
        return []

    result = []
    for i in range(12, len(m2_data)):
        curr = m2_data[i]["value"]
        prev = m2_data[i - 12]["value"]
        if prev == 0:
            continue
        yoy = (curr - prev) / prev * 100
        result.append({
            "date": m2_data[i]["date"],
            "value": curr,
            "yoy_pct": round(yoy, 2),
        })
    return result
