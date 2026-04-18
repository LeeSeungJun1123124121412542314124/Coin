"""CMC data-api v3 기반 알트코인 시즌 지수 컬렉터."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_CMC_CHART_URL = "https://api.coinmarketcap.com/data-api/v3/altcoin-season/chart"


def _season_label(value: int) -> str:
    """지수 값 → 3단계 시즌 라벨."""
    if value >= 75:
        return "altcoin_season"
    if value >= 25:
        return "neutral"
    return "bitcoin_season"


@cached(ttl=3600, key_prefix="altcoin_season")
async def fetch_altcoin_season() -> dict | None:
    """CMC data-api에서 알트코인 시즌 지수 + 90일 히스토리 조회 (1시간 캐시).

    Returns:
        {
            "index_value": int,          # 현재 지수 0-100
            "season_label": str,         # altcoin_season | neutral | bitcoin_season
            "history": [{"date": str, "value": int}, ...],  # 90일 일별
            "cached_at": str,            # ISO8601 UTC
            "is_stale": bool,            # 항상 False (캐시 히트 시에는 반환 안 됨)
        }
        None 반환 시 프론트엔드는 캐시된 마지막 데이터를 사용한다.
    """
    now = int(time.time())
    start = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp())

    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = await client.get(
                _CMC_CHART_URL,
                params={"start": start, "end": now},
            )
            resp.raise_for_status()
            data = resp.json()

        points = data.get("data", {}).get("points", [])
        if not points:
            logger.warning("altcoin_season: CMC 응답에 points 없음")
            return None

        # 최신 포인트 = 현재 지수
        latest = points[-1]
        index_value = int(float(latest["altcoinIndex"]))

        # 90일 히스토리 — 일별 (timestamp → MM/DD)
        history = [
            {
                "date": datetime.fromtimestamp(int(p["timestamp"]), tz=timezone.utc).strftime("%m/%d"),
                "value": int(float(p["altcoinIndex"])),
            }
            for p in points
        ]

        return {
            "index_value": index_value,
            "season_label": _season_label(index_value),
            "history": history,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "is_stale": False,
        }

    except httpx.HTTPStatusError as e:
        logger.warning("altcoin_season HTTP 오류: %s", e.response.status_code)
        return None
    except Exception as e:
        logger.warning("altcoin_season 조회 실패: %s", e)
        return None
