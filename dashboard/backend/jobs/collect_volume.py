"""거래량 수집 — 매일 00:10 UTC (KST 09:10, KRX 마감 후).

업비트/빗썸/KRX 거래대금을 수집하여 volume_daily 테이블에 저장.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def collect_volume() -> None:
    """거래소 거래량 수집 (Phase 3에서 구현)."""
    logger.info("거래량 수집 시작")
    # TODO: Phase 3 — upbit/bithumb collector 연동
