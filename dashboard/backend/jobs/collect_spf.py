"""SPF 데이터 수집 — 매일 00:10 UTC.

OI, FR, BTC 가격을 수집하여 spf_records 테이블에 저장.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def collect_spf() -> None:
    """OI/FR/BTC 일별 레코드 수집 및 저장 (Phase 2에서 구현)."""
    logger.info("SPF 수집 시작")
    # TODO: Phase 2 — binance_derivatives collector 연동
