"""대시보드 공통 데이터 조회 유틸."""
from __future__ import annotations
import logging

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)


def _fear_greed_label(value: int) -> str:
    if value <= 25:
        return "극단적 공포"
    if value <= 50:
        return "공포"
    if value <= 75:
        return "탐욕"
    return "극단적 탐욕"


@cached(ttl=300, key_prefix="fear_greed")
async def get_fear_greed() -> dict | None:
    """봇의 DataCollector.fetch_fear_greed() 재활용. (5분 캐시)"""
    from app.data.data_collector import DataCollector

    try:
        collector = DataCollector()
        value = await collector.fetch_fear_greed()
        if value is None:
            return None
        return {"value": value, "label": _fear_greed_label(value)}
    except Exception as e:
        logger.error("Fear & Greed 조회 실패: %s", e)
        return None


@cached(ttl=300, key_prefix="onchain")
async def get_onchain() -> dict | None:
    """봇의 DataCollector.fetch_onchain_data() 재활용. (5분 캐시)"""
    from app.data.data_collector import DataCollector

    try:
        collector = DataCollector()
        return await collector.fetch_onchain_data("btc")
    except Exception as e:
        logger.error("온체인 조회 실패: %s", e)
        return None
