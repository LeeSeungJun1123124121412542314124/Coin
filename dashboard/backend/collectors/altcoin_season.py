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
    """CMC data-api에서 알트코인 시즌 지수 + 365일 데이터 조회 (1시간 캐시)."""
    now = int(time.time())
    start_365 = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())

    try:
        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = await client.get(
                _CMC_CHART_URL,
                params={"start": start_365, "end": now},
            )
            resp.raise_for_status()
            data = resp.json()

        points = data.get("data", {}).get("points", [])
        if not points:
            logger.warning("altcoin_season: CMC 응답에 points 없음")
            return None

        # 현재 지수 (최신 포인트)
        latest = points[-1]
        index_value = int(float(latest["altcoinIndex"]))

        # 90일 히스토리 (차트용) — market_cap 포함
        history_raw = points[-90:] if len(points) >= 90 else points
        history = [
            {
                "date": datetime.fromtimestamp(int(p["timestamp"]), tz=timezone.utc).strftime("%m/%d"),
                "value": int(float(p["altcoinIndex"])),
                "market_cap": float(p.get("altcoinMarketcap") or 0),
            }
            for p in history_raw
        ]

        # 과거 시점별 값
        def _val_at(days_ago: int) -> int | None:
            idx = len(points) - 1 - days_ago
            return int(float(points[idx]["altcoinIndex"])) if idx >= 0 else None

        # 연간 고저
        def _extreme(fn) -> dict:
            p = fn(points, key=lambda x: float(x["altcoinIndex"]))
            v = int(float(p["altcoinIndex"]))
            dt = datetime.fromtimestamp(int(p["timestamp"]), tz=timezone.utc)
            return {
                "value": v,
                "date": dt.strftime("%b %d, %Y"),
                "season_label": _season_label(v),
            }

        return {
            "index_value": index_value,
            "season_label": _season_label(index_value),
            "history": history,
            "yesterday_value": _val_at(1),
            "last_week_value": _val_at(7),
            "last_month_value": _val_at(30),
            "yearly_high": _extreme(max),
            "yearly_low": _extreme(min),
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "is_stale": False,
        }

    except httpx.HTTPStatusError as e:
        logger.warning("altcoin_season HTTP 오류: %s", e.response.status_code)
        return None
    except Exception as e:
        logger.warning("altcoin_season 조회 실패: %s", e)
        return None
